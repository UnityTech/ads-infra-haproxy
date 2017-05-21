#!/bin/sh

#
# - drop SYN packets
# - pause a bit
#
iptables -I INPUT -p tcp -m multiport —dports 80,443 —syn -j DROP
sleep 1

#
# - reload haproxy
# - un-drop SYN packets
#
PID=/data/proxy.pid
/usr/local/sbin/haproxy -p $PID -f /data/proxy.cfg -D -sf $(cat $PID)
iptables -D INPUT -p -tcp -m multiport —dports 80,443 —syn -j DROP

#
# - idle the wrapper script as long as the process is running
# - please note haproxy will run in the background
# - if somehow haproxy dies the wrapper script will fail and the pod will restart it
#
while ls /proc/$(cat /data/proxy.pid); do sleep 1; done
exit 1
