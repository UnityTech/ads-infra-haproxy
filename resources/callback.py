#!/usr/bin/python

import hashlib
import json
import os
import requests
import shell
import sys

from jinja2 import Template

"""
Simple re-configuration sequence for all the proxies managed by this tier. Any slave minus the
proxies will be turned into a map of IP address arrays. The actual re-configuration (via a
automaton state-machine transition) is executed if the MD5 digest of the latest set of slaves
differs from the previous one.

@todo what to do upon a configuration request failure?
"""

if __name__ == '__main__':

    #
    # - retrieve the latest set of pods via $PODS
    # - retrieve the latest state if any via $STATE
    # - build the map of arrays
    #
    pods = json.loads(os.environ['PODS'])
    keys = set([pod['app'] for pod in pods])
    last = json.loads(os.environ['STATE']) if 'STATE' in os.environ else {'md5': None}
    hosts = {key:[] for key in keys}
    for pod in pods:
        hosts[pod['app']].append(pod['ip'])

    #
    # - blindly update Route53 with a single A record
    # - this record will hold 1+ external IPs for all the haproxies
    # - this code path is conditional to having the proper annotation set
    #
    # @todo what about other providers? how do we fold that in?
    #
    js = json.loads(os.environ['KONTROL_ANNOTATIONS'])
    if 'haproxy.unity3d.com/route53' in js:

        raw = \
        """
        {
            "Changes": [
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": "{{domain}}",
                    "Type": "A",
                    "TTL": 60,
                    "ResourceRecords": {{values}}
                }
            }]
        }
        """

        #
        # - extract the zone ID + the domain name
        # - render our little jinja2 template (e.g the AWS CLI json request blurb)
        # - use the external IP reported by each proxy pod in its payload
        #
        tokens = js['haproxy.unity3d.com/route53'].split(':')
        ips = [pod['payload']['eip'] for pod in pods if pod['app'] == 'haproxy']
        with open('/data/route53.js', 'wb') as fd:
            fd.write(Template(raw).render(domain=tokens[1], values=json.dumps([{'Value': ip} for ip in ips])))

        #
        # - fire the request by invoking the CLI
        #
        print >> sys.stderr, 'A record (%s) updated with %s' % (tokens[1], ', '.join(ips))
        shell.shell('aws route53 change-resource-record-sets --hosted-zone-id %s --change-batch file:///data/route53.js' % tokens[0])

    #
    # - keep the HAProxy pods apart
    # - remove them from the map
    #
    proxies = hosts['haproxy']
    del hosts['haproxy']

    #
    # - compare the latest MD5 digest for that map with what
    #   was in the previous state
    # - if there is no difference exit now
    #
    hasher = hashlib.md5()
    hasher.update(json.dumps(hosts))
    md5 = ':'.join(c.encode('hex') for c in hasher.digest())
    if md5 == last['md5']:

        print >> sys.stderr, 'no downstream changes, skipping'
        sys.exit(0)

    def _http(ip, cmd):
        try:
            url = 'http://%s:8000/script' % ip
            reply = requests.put(url, data=json.dumps({'cmd': cmd}), headers={'Content-Type':'application/json'})
            reply.raise_for_status()
            return reply.text

        except Exception:
            return None

    #
    # - we got a change
    # - fire a request to flip each proxy automaton to 'configure'
    # - pass the latest map of IP arrays as the argument
    # - update the state by printing it to stdout
    #
    print >> sys.stderr, '1+ downstream hosts changed, asking #%d proxies to re-configure' % len(proxies)
    replies = [_http(ip, "echo WAIT configure '%s' | socat -t 60 - /tmp/sock" % json.dumps(hosts)) for ip in proxies]
    assert all(reply == 'OK' for reply in replies)
    state = \
    {
        'md5': md5,
        'hosts': hosts
    }

    print json.dumps(state)