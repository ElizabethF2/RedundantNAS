import time, os, sys, stat, shutil, json, base64, tempfile, subprocess, libnas

# Settings
Commit_File = 'commits.json'
Include_Paths = [
                  '/home/example/Documents',


                ]

Exclude_Paths = [

                ]
Max_Commit_Files = 90000
Max_Commit_Size = 2*(1024**3)
Delete_Threshold = 0.5
c7z_Path = r'C:\Program Files\7-zip\7z'
c7z_Password = 'e5PGKb4ZpdVv'
NAS_dir = 'Projects/AutonomousNAS'
NAS = libnas.NAS(
                 server_url = 'https://example.org:1234',
                 password = '3W1m3FwXYnwS',
                 cert_path = '../cert.pem'
                )


def sizeof_fmt(num, suffix='B'):
  for unit in ['','K','M','G','T','P','E','Z']:
      if abs(num) < 1024.0:
          return "%3.1f%s%s" % (num, unit, suffix)
      num /= 1024.0
  return "%.1f%s%s" % (num, 'Y', suffix)

def is_excluded(path):
  for ep in Exclude_Paths:
     if path.startswith(ep):
       return True
  return False

# def check_print_size(cmd, file):
  # clr = (50*'\b')+(50*' ')+(50*'\b')
  # with open(os.devnull, 'w') as devnull:
    # proc = subprocess.Popen(cmd, stdout=devnull)
    # while True:
      # time.sleep(10)
      # size = 0
      # try: size += os.path.getsize(file)
      # except: pass
      # try: size += os.path.getsize(file+'.tmp')
      # except: pass
      # sys.stdout.write(clr+'Current Size: '+sizeof_fmt(size))
      # r = proc.poll()
      # if r == 0: return sys.stdout.write(clr)
      # if r is not None and r != 0: raise subprocess.CalledProcessError(r, cmd)

def check_progress(cmd, num_files):
  if num_files < 1: num_files = 1
  clr = (10*'\b')+(10*' ')+(10*'\b')
  proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
  buf = ''
  while True:
    buf += proc.stdout.readline()
    sys.stdout.write(clr + ('%3.1f%%' % ((100.0*buf.count('Compressing'))/num_files)))
    r = proc.poll()
    if r == 0: return sys.stdout.write(clr)
    if r is not None and r != 0:
      print buf
      raise subprocess.CalledProcessError(r, cmd)

print '\n   -= AutonomousNAS =-'
print 'Loading commits...'
with open(Commit_File, 'r') as f:
  data = json.loads(f.read())
commits = data['commits']

print 'Listing local files and empty folders...'
hd_files, empty_folders = {}, {}
real_commit_file = os.path.realpath(Commit_File)
for path in Include_Paths:
  for root, dirs, files in os.walk(path):
   if is_excluded(root): continue
   for f in files:
     p = os.path.join(root, f)
     if p == real_commit_file: continue
     st = os.stat(p)
     hd_files[p] = {'size': st.st_size, 'mtime': st.st_mtime}
   if len(dirs) < 1 and len(files) < 1:
     st = os.stat(root)
     empty_folders[root] = {'size': st.st_size, 'mtime': st.st_mtime}
print ' * Local Files: ' + str(len(hd_files))
print ' * Empty Folders: ' + str(len(empty_folders))

print 'Listing files that were already committed...'
committed_files = {}
commits_by_date = sorted(commits.keys(), key=lambda k: commits[k]['date'])
for c in commits_by_date:
  for file in commits[c]['files']:
    committed_files[file] = c
  for file in commits[c]['deleted']:
    try: del committed_files[file]
    except KeyError: pass
print ' * Previously Committed Files: ' + str(len(committed_files))

print 'Generating slug...'
while True:
  commit_slug = (
                 time.strftime('%Y-%m-%d_%H-%M-%S_') +
                 base64.urlsafe_b64encode(os.urandom(3))
                )
  if commit_slug not in commits: break
print ' * Slug: ' + commit_slug

print 'Figuring out which files to commit...'
files_to_commit = {}
commit_size = 0
next_time_files, next_time_size = 0, 0
for file in sorted(hd_files):
  try: slug = committed_files[file]
  except: slug = None
  if (
      file not in committed_files or
      commits[slug]['files'][file]['size'] != hd_files[file]['size'] or
      commits[slug]['files'][file]['mtime'] != hd_files[file]['mtime']
     ):
    if commit_size < Max_Commit_Size and len(files_to_commit) < Max_Commit_Files:
      files_to_commit[file] = hd_files[file]
      committed_files[file] = commit_slug
      commit_size += hd_files[file]['size']
    else:
      next_time_files += 1
      next_time_size += hd_files[file]['size']

print 'Figuring out which files were deleted...'
deleted_files = []
for file in committed_files.keys():
  if not os.path.exists(file):
    del committed_files[file]
    deleted_files.append(file)

print 'Figuring out which old commits can be deleted...'
commits_to_delete = []
for c in commits_by_date:
  total_size = 0.0
  remaining_files = []
  remaining_size = 0.0
  for file in commits[c]['files']:
    total_size += commits[c]['files'][file]['size']
    if file in committed_files and committed_files[file] == c:
      remaining_files.append(file)
      remaining_size += commits[c]['files'][file]['size']
  if total_size == 0.0 or (remaining_size/total_size) <= Delete_Threshold:
    if (
        commit_size < Max_Commit_Size and
        len(files_to_commit) < Max_Commit_Files and
        (len(remaining_files) > 0 or len(deleted_files) > 0)
       ):
      for file in remaining_files:
        files_to_commit[file] = hd_files[file]
        commit_size += hd_files[file]['size']
      for file in commits[c]['deleted']:
        if file not in deleted_files and file not in committed_files:
          deleted_files.append(file)
      del commits[c]
      commits_to_delete.append(c)
    else:
      next_time_files += len(remaining_files)
      next_time_size += remaining_size

print 'Building commit data...'
commit = {
          'date': time.time(),
          'files': files_to_commit,
          'deleted': deleted_files
         }
print ' * Commit Size: ' + sizeof_fmt(commit_size)
print ' * Commit File(s): ' + str(len(files_to_commit))
print ' * Deleted File(s): ' + str(len(commit['deleted']))
print ' * Size of next commit(s): ' + sizeof_fmt(next_time_size)
print ' * File(s) for next commit(s): ' + str(next_time_files)
print ' * Deleted Commit(s): ' + str(len(commits_to_delete))

print 'Checking commit...'
try:
  old_empty_folders = data['empty_folders']
except:
  old_empty_folders = {}
if (
    len(commit['files']) > 0 or
    len(commit['deleted']) > 0 or
    empty_folders != old_empty_folders
   ):
  print 'Changes have been made. Storing commit...'

  print 'Serializing commits...'
  commits[commit_slug] = commit
  data['empty_folders'] = empty_folders
  commits_json = json.dumps(data, encoding='latin1')

  print 'Creating temp dir...'
  temp_dir = tempfile.mkdtemp()
  temp_commit_file = os.path.join(temp_dir, Commit_File)
  commit_arch = os.path.join(temp_dir, commit_slug + '.7z')
  file_list = os.path.join(temp_dir, 'file_list.txt')
  with open(file_list, 'w') as f:
    for file in files_to_commit:
      f.write(file + '\n')
  print ' * Temp Dir: ' + temp_dir

  print 'Storing commits to temp file...'
  with open(temp_commit_file, 'w') as f:
    f.write(commits_json)

  print 'Encrypting and compressing commit...'
  base_cmd = '"' + c7z_Path + '" a "' + commit_arch + '" -mhe -mx=9 -p' + c7z_Password + ' -scsWIN '
  check_progress(base_cmd + temp_commit_file, 1)
  check_progress(base_cmd + ' -spf @"' + file_list + '"', len(files_to_commit))

  print 'Uploading commit to NAS...'
  commit_arch_size = os.path.getsize(commit_arch)
  def cb(progress): print (
                           'Uploading' +
                           ('     %.3f%%     (' % (100.0*progress/commit_arch_size)) +
                           sizeof_fmt(progress) + ' of ' + sizeof_fmt(commit_arch_size) + ')'
                          )
  NAS.upload_file(commit_arch, NAS_dir + '/' + commit_slug + '.7z', callback=cb)

  print 'Removing old commits marked for deletion...'
  for c in commits_to_delete:
    print 'Deleting ' + c + '...'
    NAS.remove(NAS_dir + '/' + c + '.7z')

  print 'Storing commits to file...'
  with open(Commit_File, 'w') as f:
    f.write(commits_json)

  print 'Deleting temp dir...'
  shutil.rmtree(temp_dir)
else:
  print 'No changes have been made. Commit will be discarded.'

print 'Done!'
