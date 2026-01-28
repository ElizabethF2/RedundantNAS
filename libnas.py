import requests, time, json, hashlib, os, stat

class NAS_Timeout(Exception): pass
class NAS_Error(Exception): pass

class NAS():
  server_url, password, cert_path, Max_Time_To_Retry = None, None, None, (60*60)

  def __init__(self, server_url, password, cert_path):
    self.server_url = server_url
    self.password = password
    self.cert_path = cert_path

  def hash_file(self, path):
    sha1 = hashlib.sha1()
    with open(path, 'rb') as f:
      while True:
        data = f.read(64*1024)
        if not data:
          break
        sha1.update(data)
    return sha1.hexdigest()

  def __call_api(self, verb, uri, headers=None, payload=None, json=True, async_flow=False):
    hdrs = {'x-client-pass': self.password}
    if headers is not None:
      hdrs.update(headers)
    if not async_flow:
      uri = self.server_url + uri
      start = time.time()
      while True:
        try:
          r = requests.__dict__[verb.lower()](uri,
                                              data=payload,
                                              headers=hdrs,
                                              # verify=self.cert_path
                                              verify=False
                                              )
          if json:
            r = r.json()
            if 'error' in r:
              raise NAS_Error(r['error'])
            return r
          else:
            return r.content
        except Exception as ex:
          if isinstance(ex, NAS_Error):
            raise ex
          if (time.time()-start) > self.Max_Time_To_Retry:
            raise NAS_Timeout()
    else:
      id = self.__call_api('GET', '/id')['id']
      hdrs['x-result-id'] = id
      make_request_this_iteration = True
      while True:
        if make_request_this_iteration:
          self.__call_api(verb, uri, hdrs, payload, json=False)
        try:
          r = self.__call_api('GET', '/result/'+id)['result']
          break
        except NAS_Error as ex:
          if ex.message == 'NOT_FOUND':
            make_request_this_iteration = True
          if ex.message == 'PENDING':
            make_request_this_iteration = False
      if 'error' in r:
        raise NAS_Error(r['error'])
      return r

  def version(self):
    return self.__call_api('GET', '/version')['version']

  def metadata(self):
    return self.__call_api('GET', '/metadata')

  def sanity(self):
    return self.__call_api('GET', '/sanity')['sanity_report']

  def list_dir(self, path):
    return self.__call_api('GET', '/file/' + path)['contents']

  def download_file(self, remote_path, local_path, callback=None):
    r = requests.get(
                     self.server_url + '/file/' + remote_path,
                     headers = {'x-client-pass': self.password},
                     # verify = self.cert_path,
                     verify = False,
                     stream=True)
    if r.status_code != 200 and r.status_code != 206:
      jbuf = ''
      for chunk in r.iter_content(chunk_size=2048):
        jbuf += chunk
      raise NAS_Error(json.loads(jbuf)['error'])
    else:
      with open(local_path, 'wb') as f:
        progress = 0
        for chunk in r.iter_content(chunk_size=(1024**2)):
          f.write(chunk)
          progress += len(chunk)
          if callback: callback(progress)

  def create_dir(self, path):
    self.__call_api('POST','/file/'+path, payload='{}', async_flow=True)

  def __crupdate_file(self, verb, local_path, remote_path, callback):
    st = os.stat(local_path)
    hash = self.hash_file(local_path)
    m = {'size': st[stat.ST_SIZE], 'mtime':st[stat.ST_MTIME], 'SHA1': hash}
    self.__call_api(verb, '/file/' + remote_path, payload=json.dumps(m), async_flow=True)
    if st[stat.ST_SIZE] > 0:
      with open(local_path, 'rb') as f:
        progress = 0
        while True:
          chunk = f.read(100*1024*1024)
          if not chunk:
            break
          chash = hashlib.sha1(chunk).hexdigest()
          self.__call_api(
                          'PUT', '/chunk/'+remote_path,
                          headers = {'x-chunk-hash': chash},
                          payload=chunk,
                          async_flow=True
                         )
          progress += len(chunk)
          if callback: callback(progress)

  def upload_file(self, local_path, remote_path, callback=None):
    self.__crupdate_file('POST', local_path, remote_path, callback)

  def update_file(self, local_path, remote_path, callback=None):
    self.__crupdate_file('PUT', local_path, remote_path, callback)

  def move_file(self, source, destination):
    self.__call_api('PUT', '/move/file/'+source+'?to='+destination, async_flow=True)

  def remove(self, path):
    self.__call_api('DELETE', '/file/'+path, async_flow=True)
