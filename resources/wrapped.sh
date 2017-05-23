#!/bin/sh

#
# - find out on what ports the proxy is configured to bind
# - those ports are extracted from /data/proxy.cfg
#
for_each_port()
{
    grep bind /data/proxy.cfg | while read -r line; do
        port=$(echo $line | cut -d ":" -f2)
        eval $1
    done
}

#
# - drop SYN packets by injecting a new rule for each port
#
for_each_port 'iptables -I INPUT -p tcp --dport $port -i eth0 --tcp-flags SYN,ACK,FIN,RST SYN -j DROP && 
echo disabled SYN packets on TCP $port'

#
# - pause a bit
# - reload haproxy
# - any warning will land in /data/proxy.out
#
sleep 1
PID=/data/proxy.pid
/usr/local/sbin/haproxy -p $PID -f /data/proxy.cfg -D -sf $(cat $PID) > /data/proxy.out 2>&1
echo proxy (re-)started as PID $PID

#
# - re-enable SYN packets on the ports
#
for_each_port 'iptables -D INPUT -p tcp --dport $port -i eth0 --tcp-flags SYN,ACK,FIN,RST SYN -j DROP &&
echo enabled SYN packets on TCP $port'

#
# - idle the wrapper script as long as the process is running
# - please note haproxy will run in the background
# - if somehow haproxy dies the wrapper script will fail and the pod will restart it
#
while ls /proc/$(cat /data/proxy.pid); do sleep 1; done
exit 1
