# ToDo: delete, help, search

import sys, os, datetime, tempfile
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))
import libnas

try: raw_input
except: raw_input = input

working_directory = ''
clipboard = []



NAS = libnas.NAS(server_url = sys.argv[1],
                 password = sys.argv[2],
                 cert_path = sys.argv[3])

def sizeof_fmt(num, suffix='B'):
  for unit in ['','K','M','G','T','P','E','Z']:
      if abs(num) < 1024.0:
          return "%3.1f%s%s" % (num, unit, suffix)
      num /= 1024.0
  return "%.1f%s%s" % (num, 'Y', suffix)

def relpath(p):
  r = []
  if p.startswith('/'):
    p = p[1:]
  elif len(working_directory):
    r = working_directory.split('/')
  for i in p.split('/'):
    if i == '..':
      try: r.pop()
      except IndexError: pass
    elif i != '':
      r.append(i)
  return '/'.join(r)

def parse(cmd):
  global working_directory, clipboard

  cmd = cmd.split(' ')
  command = cmd[0].lower()

  aliases = {
    'l': 'ls',
    'dir': 'ls',
    'c': 'cd',
    'g': 'get',
    'p': 'put',
    'v': 'version',
    'p': 'put',
    'u': 'update',
    'h': 'help',
    '?': 'help',
    'm': 'move',
    'mv': 'move',
    'r': 'move',
    'rename': 'move',
    'ren': 'move',
    's': 'sanity'
  }

  try:
    command = aliases[command]
  except KeyError:
    pass

  quoted_arg = False
  args = []
  for a in cmd[1:]:
    if quoted_arg and a.endswith('"'):
      args.append(quoted_arg + ' ' + a[:-1])
      quoted_arg = False
    elif quoted_arg:
      quoted_arg += ' ' + a
    elif a.startswith('"'):
      quoted_arg = a[1:]
    else:
      args.append(a)

  if command == 'version':
    print(NAS.version())
  elif command == 'sanity':
    print(NAS.sanity())
  elif command == 'help':
    print('TODO: put actual help text here')
  elif command == 'ls':
    r = NAS.list_dir(working_directory)
    for k in sorted(r.keys()):
      try:
        print(' '.join([k.split('/')[-1],
              datetime.datetime.utcfromtimestamp(r[k]['mtime']).strftime('%Y-%m-%d %H:%M:%S'),
              sizeof_fmt(r[k]['size']),
              r[k]['SHA1'][:8]]))
      except KeyError:
        print(k.split('/')[-1])
  elif command == 'cd':
    working_directory = relpath(args[0])
  elif command == 'get':
    lpath = args[0].split('/')[-1]
    if os.path.exists(lpath):
      print('Error: A local file with that name already exists')
    else:
      rpath = relpath(args[0])
      print('Downloading ' + args[0] + ' ...')
      def cb(p): sys.stdout.write('\r'+sizeof_fmt(p)+'      '); sys.stdout.flush()
      NAS.download_file(rpath, lpath, cb)
      print('')
  elif command == 'put' or command == 'update':
    rpath = relpath(os.path.basename(args[0]))
    def cb(p): sys.stdout.write('\r'+sizeof_fmt(p)+'      '); sys.stdout.flush()
    if command == 'put':
      NAS.upload_file(args[0], rpath, cb)
    elif command == 'update':
      NAS.update_file(args[0], rpath, cb)
    print('')
  elif command == 'cut':
    clipboard = map(relpath, args)
    print('Selected ' + str(len(clipboard)) + ' file(s)')
  elif command == 'paste':
    for f in clipboard:
      dest = relpath(f.split('/')[-1])
      NAS.move_file(f, dest)
    print('Moved ' + str(len(clipboard)) + ' file(s)')
    clipboard = []
  elif command == 'move':
    NAS.move_file(relpath(args[0]), relpath(args[1]))
  elif command == 'mkdir':
    NAS.create_dir(relpath(args[0]))
  else:
    print('Invalid command')

def interpreter():
  while True:
    inp = raw_input(working_directory + ' )> ')
    if inp == 'exit':
      return
    try: parse(inp)
    except Exception as ex: print('Error:', ex)

if __name__ == '__main__':
  interpreter()
