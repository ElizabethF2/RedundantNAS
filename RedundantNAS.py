import sys, os, stat, thread, threading, logging, traceback
import time, random, json, hashlib, base64
import socket, ssl, SocketServer, BaseHTTPServer, urllib, urllib2
import urlparse, requests, mimetypes, smtplib, email.mime.text

# Set working directory to script path
script_path = os.path.abspath(sys.argv[0])
script_dir = os.path.dirname(script_path)
os.chdir(script_dir)

# Initialize the global state
state = {
  'results_dict': {},
  'last_request': time.time(),
  'last_dns_update': 0,
  'sanity_report': 'A sanity check has not been preformed since the server was restarted.\nPlease wait for one to be run automatically.',
  'hd_replace_notified': False,
  'insane': False
}

# Load the config to memory
with open('config.json','r') as f:
  state['config'] = json.loads(f.read())

# Setup Logging
logging.basicConfig(filename=state['config']['Paths']['Log'],
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    level='INFO')
def log_exception_handler(type, value, tb):
  logging.exception('Uncaught exception: ' + str(value) + '\n' + '\n'.join(traceback.format_tb(tb)))
sys.excepthook = log_exception_handler
logging.info('Starting up...')

# Find and Setup HD Root
state['config']['Exclude_Paths'].append(state['config']['Paths']['Parent_Dir'])
if not script_dir.endswith(state['config']['Paths']['Parent_Dir']):
  logging.error('Scipt directory doesn\'t match base directory. Shutting down.')
  logging.shutdown()
  exit()
state['hd_root'] = script_dir[:-len(state['config']['Paths']['Parent_Dir'])]

# Load metadata
with open(state['config']['Paths']['Metadata'], 'r') as f:
  state['metadata'] = json.loads(f.read())

# Generate version string
with open(script_path, 'rb') as f:
  state['version_str'] = hashlib.sha1(f.read()).hexdigest()

generate_id = lambda: base64.urlsafe_b64encode(os.urandom(39))

def has_key_case_insensitive(k, d):
  for i in d:
    if k.lower() == i.lower():
      return True
  return False

def is_valid_filename(name):
  valid_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_ !@#$%^&()\'.,~`'
  for c in name:
    if c not in valid_chars:
      return False
  return True

def is_excluded(path):
  for ep in state['config']['Exclude_Paths']:
    if path.startswith(ep + '/') or path == ep:
      return True
  return False

# Returns dict with metadata or None if invalid
def parse_metadata(data):
  try:
    inp = json.loads(data)
    if len(inp) == 0: return {}
    return {
      'SHA1': str(inp['SHA1']),
      'size': int(inp['size']),
      'mtime': int(inp['mtime'])
    }
  except:
    return None

def commit_metadata():
  metadata_str = json.dumps(state['metadata'])
  os.rename(state['config']['Paths']['Metadata'], state['config']['Paths']['Metadata']+'.bak')
  with open(state['config']['Paths']['Metadata'], 'w') as f:
    f.write(metadata_str)

def hash_file(path):
  sha1 = hashlib.sha1()
  with open(path, 'rb') as f:
    while True:
      data = f.read(64*1024)
      if not data:
        break
      sha1.update(data)
  return sha1.hexdigest()

def move_to_trash(path, reason):
  while True:
    id = generate_id()
    if id not in state['metadata']['trash']:
      break
  real_path = os.path.join(state['hd_root'], path)
  trash_path = os.path.join(state['config']['Paths']['Trash'], id)
  state['metadata']['trash'][id] = {
    'original_path': real_path,
    'reason': reason,
    'metadata': state['metadata']['files'][path]
  }
  os.rename(real_path, trash_path)
  del state['metadata']['files'][path]

def send_email(subject, msg):
  subject = '[RedundantNAS] ' + subject
  msg += '\n\nRegards,\n' + state['config']['Email']['Friendly_Name']
  logging.info('Sending email...\nSubject: ' + subject + '\n' + msg)
  try:
    m = email.mime.text.MIMEText(msg)
    m['Subject'] = subject
    m['From'] = state['config']['Email']['User']
    recipient = ", ".join(state['config']['Email']['Recipients'])
    m['to'] = recipient
    if state['config']['Email']['SSL']:
      s = smtplib.SMTP_SSL(state['config']['Email']['Host']+':'+str(state['config']['Email']['Port']))
    else:
      s = smtplib.SMTP(state['config']['Email']['Host']+':'+str(state['config']['Email']['Port']))
    if state['config']['Email']['TLS']:
      s.starttls()
    s.login(state['config']['Email']['User'], state['config']['Email']['Password'])
    s.sendmail(state['config']['Email']['User'], recipient, m.as_string())
    s.close()
    logging.info('Message sent!')
  except Exception as ex:
    logging.error('Error sending email!   ' + str(ex))

def call_api(verb, uri, headers=None, payload=None, json=True, async_flow=False):
  hdrs = {'x-server-pass': state['config']['Passwords']['Server']}
  if headers is not None:
    hdrs.update(headers)
  if not async_flow:
    uri = state['config']['Other_Server_URL'] + uri
    start = time.time()
    while True:
      try:
        r = requests.__dict__[verb.lower()](uri,
                                            data=payload,
                                            headers=hdrs,
                                            verify=state['config']['Paths']['Cert']
                                            )
        return (r.json() if json else r.content)
      except Exception as ex:
        if (time.time()-start) > state['config']['Max_Time_To_Retry']:
          notify_insane('API call failed for too long.   ' + verb + '   ' + uri, True)
  else:
    id = call_api('GET', '/id')['id']
    hdrs['x-result-id'] = id
    r = {'error':'NOT_FOUND'}
    while True:
      if 'error' in r and r['error'] == 'NOT_FOUND':
        call_api(verb, uri, hdrs, payload, json=False)
      r = call_api('GET', '/result/'+id)
      if 'result' in r:
        return r['result']

def notify_insane(reason, propigate):
  logging.error('System Insane!   Reason: ' + reason)
  send_email('Integrity Check Failed', 'An integrity check failed and the servers were shutdown.\nCheck the logs for details.')
  state['insane'] = True
  state['server'].socket.close()
  state['server'].shutdown()
  if propigate:
    while True:
      try:
        r = call_api('POST', '/notify_insane')
        if not r['success']:
          continue
        break
      except:
        continue

def upkeep_worker(state):
  while True:
    time.sleep(10)
    now = time.time()

    # HD Replace Worker
    if (not state['hd_replace_notified'] and
        now > state['config']['HD_Replace_Date']):
      send_email(
        'Hard drive needs to be replaced',
        'The hard drive has exceeded it\'s lifetime and will need to be replaced soon.'
      )
      state['hd_replace_notified'] = True

    # DNS Update Worker
    if (now - state['last_dns_update']) > state['config']['DNS']['Frequency']:
      try:
        urllib2.urlopen(state['config']['DNS']['Update_URL']).read()
        state['last_dns_update'] = now
      except:
        pass

    # Sanity Check Worker
    if (now - state['last_request']) > state['config']['Sanity_Check']['Frequency']:
      def notify_insane_if_not_changed(reason):
        if (now - state['last_request']) > state['config']['Sanity_Check']['Frequency']:
          return notify_insane(reason, True)
      state['sanity_report'] = 'Sanity check started at ' + time.asctime() + '\n'
      start = time.time()
      if call_api('GET', '/version')['version'] != state['version_str']:
        notify_insane('Server versions don\'t match.', True)
      remote_metadata = call_api('GET', '/metadata')
      for p in state['metadata']['files']:
        if is_excluded(p):
          continue
        if p not in remote_metadata['files']:
          notify_insane_if_not_changed(p + ' not in remote metadata')
        real_path = os.path.join(state['hd_root'], p)
        if 'SHA1' in state['metadata']['files'][p]:
          if remote_metadata['files'][p]['SHA1'] != state['metadata']['files'][p]['SHA1']:
            notify_insane_if_not_changed('Hashes don\'t match for ' + p)
          if remote_metadata['files'][p]['mtime'] != state['metadata']['files'][p]['mtime']:
            notify_insane_if_not_changed('mtimes don\'t match for ' + p)
          if remote_metadata['files'][p]['size'] != state['metadata']['files'][p]['size']:
            notify_insane_if_not_changed('Sizes don\'t match for ' + p)
          if not os.path.isfile(real_path):
            notify_insane_if_not_changed(p + ' is not a real file')
          st = os.stat(real_path)
          if st[stat.ST_MTIME] != state['metadata']['files'][p]['mtime']:
            notify_insane_if_not_changed('Real mtime doesn\'t match mtime in metadata for ' + p)
          if st[stat.ST_SIZE] != state['metadata']['files'][p]['size']:
            notify_insane_if_not_changed('Real size doesn\'t match size in metadata for ' + p)
        elif not os.path.isdir(real_path):
          notify_insane_if_not_changed(p + ' is not a real directory')
      for p in remote_metadata['files']:
        if is_excluded(p):
          continue
        if p not in state['metadata']['files']:
          notify_insane_if_not_changed(p + ' not in local metadata')
      for root, subdirs, files in os.walk(state['hd_root']):
        for i in (subdirs+files):
          meta_path = os.path.join(root, i)[len(state['hd_root']):]
          if not is_excluded(meta_path):
            if meta_path not in state['metadata']['files']:
              notify_insane(meta_path + ' not in metadata', True)
      for p in random.sample(state['metadata']['files'],
                             state['config']['Sanity_Check']['Files_To_Check']):
        if 'SHA1' not in state['metadata']['files'][p]:
          continue
        if (hash_file(os.path.join(state['hd_root'], p)) !=
            state['metadata']['files'][p]['SHA1']):
          notify_insane_if_not_changed('Hash doesn\'t match for ' + p)
      state['sanity_report'] += (
                                 'Finished at ' + time.asctime() +
                                 '\nTotal Runtime: ' + str(time.time()-start) + ' second(s).\n'
                                 'Sanity: ' + ('Insane' if state['insane'] else 'Sane')
                                )
      logging.info(state['sanity_report'])
      state['last_request'] = time.time()

    # Results_Dict Garbage Collection
    for id in state['results_dict'].keys():
      if (now-state['results_dict'][id]['created']) > state['config']['Result_Expiration_Time']:
        del state['results_dict'][id]

def connection_watchdog(state):
  # state['server'].socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  while True:
    try:
      urllib2.urlopen(state['config']['Connection_Check']['URL']).read()
      time.sleep(state['config']['Connection_Check']['Frequency'])
    except:
      break
  time.sleep(state['config']['Connection_Check']['Reset_Time'])
  logging.error('Internet connection lost, resetting server')
  state['server'].socket.close()
  state['server'].shutdown()

class Request_Handler(BaseHTTPServer.BaseHTTPRequestHandler):
  def log_str(self):
    return self.client_address[0] + ':' + str(self.client_address[1]) + '   ' + self.requestline

  def response_start(self, code=200, type='text/json'):
    self.send_response(code)
    self.send_header('Content-type', type)
    self.end_headers()

  def async_init(self):
    id = self.headers.dict['x-result-id']
    state['results_dict'][id] = { 'created': time.time(), 'pending': True }
    logging.info('async_init ' + id + '   ' + self.log_str())

  def async_return(self, r):
    id = self.headers.dict['x-result-id']
    state['results_dict'][id]['result'] = r
    del state['results_dict'][id]['pending']
    self.response_start(204)
    logging.info('async_return ' + id + '   ' + repr(r))

  def handle_request(self, verb):
    state['last_request'] = time.time()
    self.connection.settimeout(state['config']['Socket_Timeout'])

    if verb != 'GET':
      logging.info(self.log_str())

    if ('x-server-pass' in self.headers.dict and
        self.headers.dict['x-server-pass'] == state['config']['Passwords']['Server']):
      type = 'Server'
    elif ('x-client-pass' in self.headers.dict and
          self.headers.dict['x-client-pass'] == state['config']['Passwords']['Client']):
      type = 'Client'
    else:
      logging.info('Unauthenticated request\n' + repr(self.__dict__))
      return

    # GET /version
    if verb == 'GET' and self.path == '/version':
      self.response_start()
      self.wfile.write(json.dumps({'version':state['version_str']}))

    # GET /id
    elif verb == 'GET' and self.path == '/id':
      self.response_start()
      self.wfile.write(json.dumps({'id':generate_id()}))

    # GET /result/{id}
    elif verb == 'GET' and self.path.startswith('/result/'):
      id = self.path.split('/')[2]
      try:
        if 'pending' in state['results_dict'][id]:
          self.response_start(404)
          self.wfile.write('{"error":"PENDING"}')
          return
        result = state['results_dict'][id]['result']
        self.response_start()
        self.wfile.write(json.dumps({'result':result}))
      except KeyError:
        self.response_start(404)
        self.wfile.write('{"error":"NOT_FOUND"}')

    # GET /metadata
    elif verb == 'GET' and self.path == '/metadata':
      self.response_start()
      self.wfile.write(json.dumps(state['metadata']))

    # GET /sanity
    elif verb == 'GET' and self.path == '/sanity':
      self.response_start()
      self.wfile.write(json.dumps({"sanity_report":state['sanity_report']}))

    # POST /notify_insane
    elif verb == 'POST' and self.path == '/notify_insane':
      self.response_start()
      self.wfile.write('{"success":true}')
      notify_insane('triggered remotely', False)

    # GET /file/{path}
    elif verb == 'GET' and self.path.startswith('/file/'):
      path = urllib.unquote(self.path[6:])
      if path.endswith('/'):
        path = path[:-1]
      if is_excluded(path):
        self.response_start(403)
        self.wfile.write('{"error":"EXCLUDED_FOLDER"}')
        return
      if path in state['metadata']['files'] or path == '':
        if path == '' or 'SHA1' not in state['metadata']['files'][path]:
          if not os.path.isdir(os.path.join(state['hd_root'], path)):
            notify_insane(path + ' isn\'t actually a directory.', True)
            return
          contents = {}
          for p in state['metadata']['files']:
            if is_excluded(p + '/'):
              continue
            if p.startswith(path + '/') and p.count('/') == (path.count('/') + (1 if path!='' else 0)):
              contents[p] = state['metadata']['files'][p]
          self.response_start()
          self.wfile.write(json.dumps({'contents':contents}))
        else:
          if 'lock' in state['metadata']['files'][path]:
            self.response_start(403)
            return self.wfile.write(json.dumps({'error':'LOCKED'}))
          real_path = os.path.join(state['hd_root'], path)
          if not os.path.isfile(real_path):
            notify_insane(path + ' isn\'t actually a file.', True)
          size = os.stat(real_path)[stat.ST_SIZE]
          start, end = 0, size
          if 'range' in self.headers.dict:
            try:
              r = self.headers.dict['range'].split('-')
              start = int(r[0])
              if len(r) > 2:
                end = int(r[2])
            except:
              return self.response_start(400)
            if start < 0 or start > size or end < 0 or end > size:
              return self.response_start(416)
            remaining = end - start
            with open(real_path, 'rb') as f:
              f.seek(start)
              self.response_start(code=206, type=mimetypes.guess_type(real_path))
              while remaining > 0:
                chunk = min(1024**2, remaining)
                remaining -= chunk
                self.wfile.write(f.read(chunk))
          else:
            self.response_start(code=200, type=mimetypes.guess_type(real_path))
            with open(real_path, 'rb') as f:
              while True:
                buf = f.read(1024**2)
                if not buf:
                  break
                self.wfile.write(buf)
      else:
        self.response_start(404)
        self.wfile.write('{"error":"NOT_FOUND"}')

    # POST or PUT /file/{path}
    elif (verb == 'POST' or verb == 'PUT') and self.path.startswith('/file/'):
      l = int(self.headers.getheader('content-length'))
      m = parse_metadata(self.rfile.read(l))
      path = urllib.unquote(self.path[6:])
      if path.endswith('/'):
        path = path[:-1]
      real_path = os.path.join(state['hd_root'], path)
      base_path, fname = os.path.dirname(real_path), os.path.basename(real_path)
      with self.server.write_lock:
        self.async_init()
        if m is None:
          return self.async_return({'error':'INVALID_METADATA'})
        if real_path != os.path.abspath(real_path):
          return self.async_return({'error':'INVALID_PATH'})
        if is_excluded(path):
          return self.async_return({'error':'EXCLUDED_FOLDER'})
        if verb == 'POST' and has_key_case_insensitive(path, state['metadata']['files']):
          return self.async_return({'error':'ALREADY_EXISTS'})
        if verb == 'PUT' and path not in state['metadata']['files']:
          return self.async_return({'error':'NOT_FOUND'})
        if verb == 'PUT' and 'lock' in state['metadata']['files'][path]:
          return self.async_return({'error':'LOCKED'})
        if verb == 'PUT' and 'SHA1' not in state['metadata']['files'][path]:
          return self.async_return({'error':'FOLDER_UNSUPPORTED'})
        if not is_valid_filename(fname) or not os.path.exists(base_path):
          return self.async_return({'error':'INVALID_PATH'})
        if verb == 'POST' and os.path.exists(real_path):
          return notify_insane(path + ' already exists.', True)
        if verb == 'PUT' and not os.path.exists(real_path):
          return notify_insane(path + ' doesn\'t exist.', True)
        if verb == 'PUT':
          move_to_trash(path, 'Update')
        state['metadata']['files'][path] = m
        if 'SHA1' in m:
          if m['size'] > 0: state['metadata']['files'][path]['lock'] = True
          with open(real_path, 'a'): pass
          os.utime(real_path, (m['mtime'],m['mtime']))
        else:
          os.mkdir(real_path)
        commit_metadata()
        if type == 'Client':
          r = call_api(verb, '/file/'+path, payload=json.dumps(m), async_flow=True)
          if 'error' in r:
            notify_insane('Error propigating   ' + repr((r,self)), True)
        return self.async_return({'success':True})

    # PUT /chunk/{path}
    elif verb == 'PUT' and self.path.startswith('/chunk/'):
      l = int(self.headers.getheader('content-length'))
      chunk = self.rfile.read(l)
      path = urllib.unquote(self.path[7:])
      real_path = os.path.join(state['hd_root'], path)
      hash = self.headers.dict['x-chunk-hash']
      with self.server.write_lock:
        self.async_init()
        if is_excluded(path):
          return self.async_return({'error':'EXCLUDED_FOLDER'})
        if path not in state['metadata']['files']:
          return self.async_return({'error':'NOT_FOUND'})
        if 'lock' not in state['metadata']['files'][path]:
          return self.async_return({'error':'NOT_LOCKED'})
        if 'SHA1' not in state['metadata']['files'][path]:
          return self.async_return({'error':'FOLDER_UNSUPPORTED'})
        if hashlib.sha1(chunk).hexdigest() != hash:
          return self.async_return({'error':'HASH_MISMATCH'})
        if not os.path.exists(real_path):
          return notify_insane(path + ' doesn\'t exist.', True)
        with open(real_path, 'a+b') as f:
          f.write(chunk)
        if os.stat(real_path)[stat.ST_SIZE] >= state['metadata']['files'][path]['size']:
          if hash_file(real_path) != state['metadata']['files'][path]['SHA1']:
            return notify_insane(path + ' hash mismatch of assembled file', True)
          del state['metadata']['files'][path]['lock']
          os.utime(real_path, (state['metadata']['files'][path]['mtime'],
                               state['metadata']['files'][path]['mtime']))
          commit_metadata()
        if type == 'Client':
          r = call_api(
                       'PUT', '/chunk/'+path,
                       headers = {'x-chunk-hash': hash},
                       payload=chunk,
                       async_flow=True
                      )
          if 'error' in r:
            return notify_insane('Error propigating   ' + repr((r,self)), True)
        return self.async_return({'success':True})

    # PUT /move/file/{path}?to={path}
    elif verb == 'PUT' and self.path.startswith('/move/file/') and '?to=' in self.path:
      u = urlparse.urlparse(self.path)
      src_path = urllib.unquote(u.path[11:])
      dest_path = urlparse.parse_qs(u.query)['to'][0]
      src_real_path = os.path.join(state['hd_root'], src_path)
      dest_real_path = os.path.join(state['hd_root'], dest_path)
      dest_base_path = os.path.dirname(dest_real_path)
      dest_fname = os.path.basename(dest_real_path)
      with self.server.write_lock:
        self.async_init()
        if is_excluded(src_path) or is_excluded(dest_path):
          return self.async_return({'error':'EXCLUDED_FOLDER'})
        if dest_real_path != os.path.abspath(dest_real_path):
          return self.async_return({'error':'INVALID_PATH'})
        if src_path not in state['metadata']['files']:
          return self.async_return({'error':'NOT_FOUND'})
        if 'lock' in state['metadata']['files'][src_path]:
          return self.async_return({'error':'LOCKED'})
        if has_key_case_insensitive(dest_path, state['metadata']['files']):
          return self.async_return({'error':'ALREADY_EXISTS'})
        if not is_valid_filename(dest_fname) or not os.path.exists(dest_base_path):
          return self.async_return({'error':'INVALID_PATH'})
        if not os.path.exists(src_real_path):
          return notify_insane(src_path + ' doesn\'t actually exist', True)
        if os.path.exists(dest_real_path):
          return notify_insane(dest_path + ' actually exists', True)
        if 'SHA1' in state['metadata']['files'][src_path]:
          os.rename(src_real_path, dest_real_path)
          state['metadata']['files'][dest_path] = state['metadata']['files'][src_path]
          del state['metadata']['files'][src_path]
          commit_metadata()
        else:
          return self.async_return({'error':'FOLDER_UNSUPPORTED'})
        if type == 'Client':
          r = call_api('PUT', '/move/file/' + src_path + '?to=' + dest_path, async_flow=True)
          if 'error' in r:
            return notify_insane('Error propigating   ' + repr((r,self)), True)
        return self.async_return({'success':True})

    # DELETE /file/{path}
    elif verb == 'DELETE' and self.path.startswith('/file/'):
      path = urllib.unquote(self.path[6:])
      real_path = os.path.join(state['hd_root'], path)
      with self.server.write_lock:
        self.async_init()
        if is_excluded(path):
          return self.async_return({'error':'EXCLUDED_FOLDER'})
        if path not in state['metadata']['files']:
          return self.async_return({'error':'NOT_FOUND'})
        if 'lock' in state['metadata']['files'][path]:
          return self.async_return({'error':'LOCKED'})
        if not os.path.exists(real_path):
          return notify_insane(path + ' doesn\'t actually exist', True)
        if 'SHA1' in state['metadata']['files'][path]:
          move_to_trash(path, 'Deleted')
        else:
          try:
            os.rmdir(real_path)
            del state['metadata']['files'][path]
          except OSError:
            return self.async_return({'error':'NOT_EMPTY'})
        commit_metadata()
        if type == 'Client':
          r = call_api('DELETE', '/file/' + path, async_flow=True)
          if 'error' in r:
            return notify_insane('Error propigating   ' + repr((r,self)), True)
        return self.async_return({'success':True})

    # Invalid Path
    else:
      logging.info('Invalid path\n' + repr(self.__dict__))

  def do_GET(self):
    return self.handle_request('GET')

  def do_POST(self):
    return self.handle_request('POST')

  def do_PUT(self):
    return self.handle_request('PUT')

  def do_DELETE(self):
    return self.handle_request('DELETE')

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
  write_lock = None

thread.start_new_thread(upkeep_worker, (state,))
while not state['insane']:
  try:
    server = ThreadedHTTPServer(('',state['config']['Port']), Request_Handler)
    server.socket = ssl.wrap_socket(server.socket,
                                    certfile=state['config']['Paths']['Cert'],
                                    keyfile=state['config']['Paths']['Key'],
                                    server_side=True)
    server.socket.settimeout(state['config']['Socket_Timeout'])
    state['server'] = server
    server.write_lock = threading.Lock()
    thread.start_new_thread(connection_watchdog, (state,))
    server.serve_forever()
  except KeyboardInterrupt:
    break

time.sleep(2)
logging.shutdown()
