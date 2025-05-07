import matplotlib.pyplot as plt
import numpy as np
import csv
import sys

fig, ax = plt.subplots()

xkey = 'Time (usec)'
ykey = 'Messages Delivered'
# ykey = 'Efficiency (AL/PL)'
# ykey = 'Bytes Received (Physical)'

for f in sys.argv[1:]:
  with open(f, newline='') as csvfile:
    reader = csv.DictReader(csvfile)

    t = []
    v = []

    for row in reader:
      t.append(float(row[xkey]))
      v.append(float(row[ykey]))
    
    ax.plot(t, v, label=f)
    ax.legend(bbox_to_anchor=(0.05, 1), loc='upper left')

ax.set(xlabel=xkey, ylabel=ykey, title='Very Interesting Plot')

ax.grid()

fig.savefig("plot.png")
