import json

with open('commits.json', 'r') as f:
  data = json.loads(f.read())

print('AutonomousNAS - Finder')
print('Enter a query or leave the line blank to exit.')
print('')

while True:
  q = input('>')
  if q == '':
    break
  q = q.lower()
  for commit in sorted(data['commits'].keys()):
    commit_already_printed = False
    for file in data['commits'][commit]['files']:
      if (
          (q.startswith('^') and q[1:] in file.lower()) or
          (q.endswith('$') and q[:-1] in file.lower()) or
          q in file.lower()
         ):
           if not commit_already_printed:
             print(commit)
             commit_already_printed = True
           print('  ' + file)
  print('')
