import sys

source, remove, out = sys.argv[1:4]

print('Removing seeds from', source)
print('If they exist in', remove)
print('And writing to', out)
input('Confirm: ')

def lines(f: str):
    return open(f).readlines()

src = lines(source)
rem = set([int(x.strip()) for x in lines(remove)])

to_out = list()
outs = 0

for line in src:
    if int(line.split(' ')[0].strip()) not in rem:
        to_out.append(line)
        outs += 1

with open(out, 'w') as file:
    file.writelines(to_out)

print('Wrote', outs, 'seeds.')
