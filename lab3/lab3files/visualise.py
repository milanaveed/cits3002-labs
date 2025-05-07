import argparse
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.ticker import AutoMinorLocator
import pandas as pd

IMAGES_PATH = Path() / "images"
IMAGES_PATH.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser(prog='Visualisation')
parser.add_argument('title', type=str, help='Name of the plot') # args.title
parser.add_argument('--csv2', type=str, help='Path to the second csv file') # args.csv2
parser.add_argument('csv1', type=str, help='Path to the first csv file') # args.csv1
args = parser.parse_args() 

# Reference: https://github.com/ageron/handson-ml3/blob/main/03_classification.ipynb
def save_fig(
    fig_id,
    tight_layout=True,
    fig_extension="png",
    resolution=300,
    bbox_inches="tight",
    pad_inches=0.3,
    **kwargs,
):
    path = IMAGES_PATH / f"{fig_id}.{fig_extension}"
    if tight_layout:
        plt.tight_layout()
    plt.savefig(
        path,
        format=fig_extension,
        dpi=resolution,
        bbox_inches=bbox_inches,
        pad_inches=pad_inches,
        **kwargs,
    )


def plot_line_chart(args):
    df1 = pd.read_csv(args.csv1)
    fig, ax = plt.subplots(figsize=(10, 5))
    plt.plot(df1['Time (usec)']/1000000, df1["Messages Delivered"], label=args.csv1)
    if args.csv2 is not None:
        df2 = pd.read_csv(args.csv2)
        plt.plot(df2['Time (usec)']/1000000, df2["Messages Delivered"], label=args.csv2)
    plt.legend(loc='lower right')
    plt.xlabel('Time (s)')
    plt.ylabel('Messages Delivered')
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    plt.title(f"{args.title}")
    save_fig(f"{args.title}", tight_layout=False)


print(args)
print()
plot_line_chart(args)