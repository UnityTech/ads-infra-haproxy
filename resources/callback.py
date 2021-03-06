#!/usr/bin/python

import hashlib
import json
import os
import random
import sys
import zerorpc

from jinja2 import Template

"""
Simple re-configuration sequence for all the proxies managed by this tier. Any slave minus the
proxies will be turned into a map of IP address arrays. The actual re-configuration (via a
automaton state-machine transition) is executed if the MD5 digest of the latest set of slaves
differs from the previous one.

@todo what to do upon a configuration request failure?
"""

if __name__ == '__main__':

    assert 'KONTROL_PORT' in os.environ, '$KONTROL_PORT undefined (bug ?)'
    port = int(os.environ['KONTROL_PORT'])

    def _rpc(ip, cmd):        
        try:

            #
            # - use zerorpc to request a script invokation against a given pod
            # - default on returning None upon failure
            #
            client = zerorpc.Client()
            client.connect('tcp://%s:%d' % (ip, port))
            return client.invoke(json.dumps({'cmd': cmd}))
            
        except Exception:
            return None

    #
    # - retrieve the latest set of pods via $PODS
    # - retrieve the latest state if any via $STATE
    # - build the map of arrays
    #
    labels = json.loads(os.environ['KONTROL_LABELS'])
    pods = json.loads(os.environ['PODS'])
    keys = set([pod['app'] for pod in pods])
    last = json.loads(os.environ['STATE']) if 'STATE' in os.environ else {'md5': None}
    hosts = {key:[] for key in keys}
    for pod in pods:
        hosts[pod['app']].append(pod['ip'])

    #
    # - keep the HAProxy pods apart
    # - remove them from the map
    #
    assert labels['app'] in hosts, 'is kontrol configured as master/slave ?'
    proxies = hosts[labels['app']]
    del hosts[labels['app']]

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

    #
    # - we got a change
    # - fire a request to flip each proxy automaton to 'configure'
    # - pass the latest map of IP arrays as the argument
    # - update the state by printing it to stdout
    #
    print >> sys.stderr, '1+ downstream hosts changed, asking #%d proxies to re-configure' % len(proxies)
    replies = [_rpc(ip, "echo WAIT configure '%s' | socat -t 60 - /tmp/sock" % json.dumps(hosts)) for ip in proxies]
    assert all(reply == 'OK' for reply in replies)
    state = \
    {
        'md5': md5,
        'hosts': hosts
    }

    #
    # - craft an external IP list, one for each proxy
    # - this data is relayed via the kontrol payload
    # - pick one of the proxies at random
    # - flip its state-machine to run the Route53 udpate script (which involves the AWS CLI)
    # - this will attempt to update the DNS information with a A record
    #
    ips = [pod['payload']['eip'] for pod in pods if pod['app'] == labels['app']]
    _rpc(random.choice(proxies), "echo WAIT expose-via-route53 '%s' | socat -t 60 - /tmp/sock" % json.dumps(ips))

    print json.dumps(state)