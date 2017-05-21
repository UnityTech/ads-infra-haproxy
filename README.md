## HAProxy+Kontrol pod

### Overview

This project is a [**Docker**](https://www.docker.com) image packaging
[**HAProxy 1.7.5**](http://www.haproxy.org/) together with
[**Kontrol**](https://github.com/UnityTech/ads-infra-kontrol). It is meant
to be included in a [**Kubernetes**](https://github.com/GoogleCloudPlatform/kubernetes)
pod.

The container will run its own control-tier which will re-configure the proxy
configuration anytime downstream listeners are added or removed. Any downstream
entity wishing to be included in the proxy configuration **must** specify this
pod as its *kontrol* master.

### Lifecycle

The HAProxy instance is driven as a regular supervisor job via the *wrapped.sh* script.
This scipt will launch a daemon proxy and keep track of its PID file. Restarting the
job will spawn a new HAProxy process and gracefully drain the old on. During this
transition SYN packets will be disabled via *iptables*. Please look at *lifecycle.yml*
for more details.

The *kontrol* callback will isolate slaves that are not HAProxy and ask the proxy pods
to re-configure using their IP addresses.

The initial state will render the various configuration files including the
[**telegraf**](https://github.com/influxdata/telegraf) one. The state will then cycle
thru one or more configuration sequences with the file written under */data*. The
proxy supervisor job is then restarted. Any change detected by *kontrol* will trip
the state-machine back to that configuration state.

### TLS support

This feature is currently not supported and is planned.

### Configuring the proxy

Configuration is done via the *haproxy.unity3d.com/config* annotation. This payload
is rendered using [**Jinja 2**](http://jinja.pocoo.org/docs/2.9/). A map of arrays holding
IP addresses for each distinct set of downstream entities reporting to the proxy is
provided as the *hosts* variable. For instance:

```
annotations:
  haproxy.unity3d.com/config: |

    frontend proxy
      bind                *:80
      default_backend     http

    backend http
      mode                http
      retries             3
      option              redispatch
      option              forwardfor
      option              httpchk GET /health
      option              httpclose
      option              httplog
      balance             leastconn
      http-check expect   status 200
      default-server      inter 5s fall 1 rise 1

      {%- for key in hosts %}
      {%- for ip in hosts[key] %}
      server {{key}}-{{loop.index}} {{ip}}:80 check on-error mark-down observe layer7 error-limit 1
      {%- endfor %}
      {%- endfor %}
```

### Building the image

Pick a distro and build from the top-level directory. For instance:

```
$ docker build -f alpine-3.5/Dockerfile .
```

### Manifest

Simply use this pod in a deployment and assign it to an array with external
access using a node-port service. For instance:

```
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: haproxy
spec:
  replicas: 1
  template:
    metadata:
      labels:
        app: haproxy
        role: balancer
        tier: traffic
      annotations:
        kontrol.unity3d.com/master: haproxy.default.svc
        kontrol.unity3d.com/opentsdb: kairosdb.us-east-1.applifier.info
        haproxy.unity3d.com/config: |

          frontend proxy
            bind            *:80
            default_backend service

          backend service
            mode tcp
            {%- for key in hosts %}
            {%- for ip in hosts[key] %}
            server {{key}}-{{loop.index}} {{ip}}:2181
            {%- endfor %}
            {%- endfor %}

    spec:
      nodeSelector:
        unity3d.com/array: front
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values: 
                    - haproxy
              topologyKey: "kubernetes.io/hostname"
      containers:
       - image: registry2.applifier.info:5005/ads-infra-haproxy-alpine-3.5
         name: zookeeper
         imagePullPolicy: Always
         ports:
         - containerPort: 80
           protocol: TCP
         - containerPort: 443
           protocol: TCP
         - containerPort: 8000
           protocol: TCP
         env:
          - name: NAMESPACE
            valueFrom:
              fieldRef:
                fieldPath: metadata.namespace
```

### Support

Contact olivierp@unity3d.com for more information about this project.