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
pod as its *kontrol* master. The proxy configuration itself is specified directly
into the pod YAML manifest.

### Lifecycle

The HAProxy instance is driven as a regular supervisor job via the *wrapped.sh* script.
This scipt will launch a daemon proxy and keep track of its PID file. Restarting the
job will spawn a new HAProxy process and gracefully drain the old on. During this
transition SYN packets will be disabled via *iptables* for each bound port (as defined
in the proxy configuration file). Please look at *lifecycle.yml* for more details.

Note the pod **must** be started with the **NET_ADMIN** capability set (otherwise the
calls to *iptables* will fail). This can be nicely done in the YAML manifest, for
instance:

```
      containers:
       - image: registry2.applifier.info:5005/ads-infra-haproxy-alpine-3.5
         name: haproxy
         imagePullPolicy: Always
         securityContext:
           capabilities:
             add:
               - NET_ADMIN
```

The *kontrol* callback will isolate slaves that are not HAProxy and ask the proxy pods
to re-configure using their IP addresses.

The initial state will render the various configuration files including the
[**telegraf**](https://github.com/influxdata/telegraf) one. The state will then cycle
thru one or more configuration sequences with the file written under */data*. The
proxy supervisor job is then restarted. Any change detected by *kontrol* will trip
the state-machine back to that configuration state.

### Statistics

The plugin run by *telegraf* will attempt to access the proxy *stats* API. Simply
enable statistics in your proxy configuration and they will be relayed automatically
to our *opentsdb* endpoint. The following configuration block is all your need:

```
listen stats
  bind :1936
  mode http
  stats enable
  stats hide-version
  stats uri /haproxy
```

### Route53 record update

You can get the proxy pods to automatically update a specific A record in Route53:
set the *haproxy.unity3d.com/route53* annotation to the domain name you wish to use.
For instance:

```
haproxy.unity3d.com/route53: haproxy.sandbox-us-east-1a.k8s-dev.applifier.info
```

The A record value will map to 1+ external IP addresses, one for each proxy pod. Please
note the specified domain **must** map to a valid Route53 hosted zone.

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
    
    listen stats
      bind                :1936
      mode                http
      stats               enable
      stats               hide-version
      stats uri           /haproxy

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

Simply use this pod in a deployment and assign it to an array with external access using a
node-port service to clamp onto the desired port. For instance:

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
            bind            *:2181
            default_backend zookeeper

          backend zookeeper
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
         name: haproxy
         imagePullPolicy: Always
         securityContext:
           capabilities:
             add:
               - NET_ADMIN
         ports:
         - containerPort: 2181
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