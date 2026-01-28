import json, socket, tempfile

with open('config.json', 'r') as f:
  config = json.loads(f.read())

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
  s.connect(('localhost', config['Port']))
  print 'The server is still running!\nClose it before continuing!'
  exit()
except socket.error:
  pass

with open(config['Paths']['Metadata'], 'r') as f:
  metadata = json.loads(f.read())

def backup_metadata():
  with tempfile.NamedTemporaryFile(
                                   prefix='RedundantNAS-metadata.',
                                   suffix='.json',
                                   delete=False
                                   ) as f:
    f.write(json.dumps(metadata))
    print 'Backed up metadata to ' + f.name

def update_metadata():
  with open(config['Paths']['Metadata'], 'w') as f:
    f.write(json.dumps(metadata))
  print 'Updated metadata.'

def restore_file():
  print 'Not implmented.'

def unlock_file():
  print 'Select a file:'
  files = []
  for file, md in metadata['files'].iteritems():
    if 'lock' in md: files.append(file)
  for i,file in enumerate(files, start=1):
    print str(i) + ') ' + file
  print ''
  idx = (int(raw_input('> ')) - 1)
  print ''
  backup_metadata()
  del metadata['files'][files[idx]]['lock']
  update_metadata()

def menu():
  print ' -= RedundantNAS Administrator CLI =- '
  print 'Select an option:'
  print '1) Restore deleted file'
  print '2) Unlock partial upload'
  print ''
  inp = raw_input('> ')
  print ''
  if inp == '1': restore_file()
  if inp == '2': unlock_file()

menu()
