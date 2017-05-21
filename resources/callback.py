#!/usr/bin/python

import hashlib
import json
import os
import requests
import sys

"""
"""

if __name__ == '__main__':

    #
    # -
    #
    pods = json.loads(os.environ['PODS'])
    keys = set([pod['app'] for pod in pods])
    last = json.loads(os.environ['STATE']) if 'STATE' in os.environ else {'md5': None}
    hosts = {key:[] for key in keys}
    for pod in pods:
        hosts[pod['app']].append(pod['ip'])

    #
    # -
    #
    proxies = hosts['haproxy']
    del hosts['haproxy']

    #
    # -
    #
    hasher = hashlib.md5()
    hasher.update(json.dumps(hosts))
    md5 = ':'.join(c.encode('hex') for c in hasher.digest())
    if md5 == last['md5']:
        sys.exit(0)

    def _http(ip, cmd):
        try:

            #
            # -
            #
            url = 'http://%s:8000/script' % ip
            reply = requests.put(url, data=json.dumps({'cmd': cmd}), headers={'Content-Type':'application/json'})
            reply.raise_for_status()
            return reply.text

        except Exception:
            return None

    #
    # -
    #
    print >> sys.stderr, '1+ hosts changed, asking for re-configuration (#%d proxies)' % len(proxies)
    replies = [_http(ip, "echo WAIT configure '%s' | socat -t 60 - /tmp/sock" % json.dumps(hosts)) for ip in proxies]
    assert all(reply == 'OK' for reply in replies)
    state = \
    {
        'md5': md5,
        'hosts': hosts
    }
    
    print json.dumps(state)