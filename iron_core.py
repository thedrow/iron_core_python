import httplib
import time
import os
try:
    import json
except:
    import simplejson as json


class IronClient:
    def __init__(self, name, version, product, host=None, project_id=None,
            token=None, protocol=None, port=None, api_version=None,
            config_file=None):
        """Prepare a Client that can make HTTP calls and return it.

        Keyword arguments:
        name -- the name of the client. Required.
        version -- the version of the client. Required.
        product -- the name of the product the client will access. Required.
        host -- the default domain the client will be requesting. Defaults
                to None.
        project_id -- the project ID the client will be requesting. Can be
                      found on http://hud.iron.io. Defaults to None.
        token -- an API token found on http://hud.iron.io. Defaults to None.
        protocol -- The default protocol the client will use for its requests.
                    Defaults to None.
        port -- The default port the client will use for its requests. Defaults
                to None.
        api_version -- The version of the API the client will use for its
                       requests. Defaults to None.
        config_file -- The config file to load configuration from. Defaults to
                       None.
        """
        config = {
                "host": None,
                "protocol": "https",
                "port": 443,
                "api_version": None,
                "project_id": None,
                "token": None,
        }
        products = {
                "iron_worker": {
                    "host": "worker-aws-us-east-1.iron.io",
                    "version": 2
                },
                "iron_mq": {
                    "host": "mq-aws-us-east-1.iron.io",
                    "version": 2
                }
        }
        if product in products:
            config["host"] = products[product]["host"]
            config["api_version"] = products[product]["version"]

        config = configFromFile(config,
                os.path.expanduser("~/.iron.json"), product)
        config = configFromEnv(config)
        config = configFromEnv(config, product)
        config = configFromFile(config, "iron.json", product)
        config = configFromFile(config, config_file, product)
        config = configFromArgs(config, host=host, project_id=project_id,
                token=token, protocol=protocol, port=port,
                api_version=api_version)

        required_fields = ["project_id", "token"]

        for field in required_fields:
            if config[field] is None:
                raise ValueError("No %s set. %s is a required field." % (field,
                    field))

        self.name = name
        self.version = version
        self.product = product
        self.host = config["host"]
        self.project_id = config["project_id"]
        self.token = config["token"]
        self.protocol = config["protocol"]
        self.port = config["port"]
        self.api_version = config["api_version"]
        self.headers = {
                "Accept": "application/json",
                "User-Agent": "%s (version: %s)" % (self.name, self.version)
        }
        if self.token:
            self.headers["Authorization"] = "OAuth %s" % self.token
        self.base_url = "%s://%s:%s/%s/" % (self.protocol, self.host,
                self.port, self.api_version)
        if self.project_id:
            self.base_url += "projects/%s/" % self.project_id
        if self.protocol == "https" and self.port != httplib.HTTPS_PORT:
            raise ValueError("Invalid port (%s) for an HTTPS request. Want %s."
                    % (self.port, httplib.HTTPS_PORT))

    def request(self, url, method, body="", headers={}, retry=True):
        """Execute an HTTP request and return a dict containing the response
        and the response status code.

        Keyword arguments:
        url -- The path to execute the result against, not including the API
               version or project ID, with no leading /. Required.
        method -- The HTTP method to use. Required.
        body -- A string or file object to send as the body of the request.
                Defaults to an empty string.
        headers -- HTTP Headers to send with the request. Can overwrite the
                   defaults. Defaults to {}.
        retry -- Whether exponential backoff should be employed. Defaults
                 to True.
        """
        if headers:
            headers = dict(list(headers.items()) + list(self.headers.items()))
        else:
            headers = self.headers

        if self.protocol == "http":
            conn = httplib.HTTPConnection(self.host, self.port)
        elif self.protocol == "https":
            conn = httplib.HTTPSConnection(self.host, self.port)
        else:
            raise ValueError("Invalid protocol.")

        url = self.base_url + url

        conn.request(method, url, body, headers)
        resp = conn.getresponse()
        result = {}
        result["body"] = resp.read()
        result["status"] = resp.status
        conn.close()

        if resp.status is httplib.SERVICE_UNAVAILABLE and retry:
            tries = 5
            delay = .5
            backoff = 2
            while resp.status is httplib.SERVICE_UNAVAILABLE and tries > 0:
                tries -= 1
                time.sleep(delay)
                delay *= backoff
                conn.request(method, url, body, headers)
                resp = conn.getresponse()
                result = {}
                result["body"] = resp.read()
                result["status"] = resp.status
                conn.close()

        if resp.status >= 400:
            message = resp.reason
            if result["body"] != "":
                try:
                    result_data = json.loads(result["body"])
                    message = result_data["msg"]
                except:
                    pass
            raise httplib.HTTPException("%s: %s (%s)" %
                    (resp.status, message, url))

        return result

    def get(self, url, headers={}, retry=True):
        """Execute an HTTP GET request and return a dict containing the
        response and the response status code.

        Keyword arguments:
        url -- The path to execute the result against, not including the API
               version or project ID, with no leading /. Required.
        headers -- HTTP Headers to send with the request. Can overwrite the
                   defaults. Defaults to {}.
        retry -- Whether exponential backoff should be employed. Defaults
                 to True.
        """
        return self.request(url=url, method="GET", headers=headers,
                retry=retry)

    def post(self, url, body="", headers={}, retry=True):
        """Execute an HTTP POST request and return a dict containing the
        response and the response status code.

        Keyword arguments:
        url -- The path to execute the result against, not including the API
               version or project ID, with no leading /. Required.
        body -- A string or file object to send as the body of the request.
                Defaults to an empty string.
        headers -- HTTP Headers to send with the request. Can overwrite the
                   defaults. Defaults to {}.
        retry -- Whether exponential backoff should be employed. Defaults
                 to True.
        """
        headers["Content-Length"] = len(body)
        return self.request(url=url, method="POST", body=body, headers=headers,
                retry=retry)

    def delete(self, url, headers={}, retry=True):
        """Execute an HTTP DELETE request and return a dict containing the
        response and the response status code.

        Keyword arguments:
        url -- The path to execute the result against, not including the API
               version or project ID, with no leading /. Required.
        headers -- HTTP Headers to send with the request. Can overwrite the
                   defaults. Defaults to an empty dict.
        retry -- Whether exponential backoff should be employed. Defaults
                 to True.
        """
        return self.request(url=url, method="DELETE", headers=headers,
                retry=retry)

    def put(self, url, body="", headers={}, retry=True):
        """Execute an HTTP PUT request and return a dict containing the
        response and the response status code.

        Keyword arguments:
        url -- The path to execute the result against, not including the API
               version or project ID, with no leading /. Required.
        body -- A string or file object to send as the body of the request.
                Defaults to an empty string.
        headers -- HTTP Headers to send with the request. Can overwrite the
                defaults. Defaults to {}.
        retry -- Whether exponential backoff should be employed. Defaults
                 to True.
        """
        return self.request(url=url, method="PUT", body=body, headers=headers,
                retry=retry)


def configFromFile(config, path, product=None):
    if path is None:
        return config
    if not os.path.exists(path):
        return config
    try:
        file = open(path, "r")
    except IOError, e:
        return config
    raw = json.loads(file.read())
    for k in raw.keys():
        if k in config:
            config[k] = raw[k]
    if product is not None:
        if product in raw:
            for k in raw[product].keys():
                config[k] = raw[product][k]
    return config


def configFromEnv(config, product=None):
    if product is None:
        product = "iron"
    for k in config.keys():
        key = "%s_%s" % (product, k)
        if key.upper() in os.environ:
            config[k] = os.environ[key.upper()]
    return config


def configFromArgs(config, **kwargs):
    for k in kwargs:
        if kwargs[k] is not None:
            config[k] = kwargs[k]
    return config
