import sys
import subprocess

print('using python {}'.format(sys.executable))

TOPOLOGIES = ['FLOODING1', 'FLOODING2', 'FLOODING3']
EXECUTION_TIME = '20m'

for topology in TOPOLOGIES:
  print('running {}'.format(topology))
  subprocess.run([sys.executable, 'sim.py', '--execution-duration',
    EXECUTION_TIME, '--stats-csv', 'stats_{}.csv'.format(topology),
    '--stats-period', '5s', topology])
