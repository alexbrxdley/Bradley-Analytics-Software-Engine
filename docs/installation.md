---
layout: page
title: Installation
sidebar: installation
---

<a id="installation-section"></a>

### Clone the Repository

```bash
git clone https://github.com/alexbrxdley/Bradley-Analytics-Software-Engine.git
```

Navigate into the project folder:

```bash
cd "Bradley Analytics Software Engine"
```

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Install Required R Packages

The engine uses R for generating visualizations. Make sure R is installed locally before running the software.

Open R and install the required packages:

```r
install.packages("tidyverse")
install.packages("ggplot2")
install.packages("hexbin")
install.packages("ggfx")
install.packages("ggimage")
install.packages("scales")
install.packages("jsonlite")
install.packages("gifski")
```

---

<a id="usage-section"></a>

## Usage

Launch the Bradley Analytics Software Engine:

**Windows:**

```bash
.\bradley.bat
```

**Mac:**

```bash
python3 python/bradley_analytics.py
```

The engine will guide you through:

1. Searching by player or team
2. Choosing a visualization (Court Graphs, Axis Graphs, or Animated)
3. Court Graphs and Animated: entering a player/team and season
   Bar Chart: choosing a stat, how many to show, season, and orientation
   Scatter Plot: choosing two stats (Y axis, then X axis), how many to show, and season
4. Selecting an accent color (team name or a color code), every visualization except Scatter Plot, which shows no color at all (images only)

Shot Chart Example:

```
Search by player, team or criteria
1. Player
2. Team
3. Criteria

Choose an option: 1

Available Visualizations

Court Graphs:
1. Shot Chart
2. Heat Map
3. Hex Shot Chart

Axis Graphs:
4. Bar Chart
5. Scatter Plot

Animated:
6. Animated Shot Chart

Choose visualization: 1

Enter player name: Jayson Tatum

Available Seasons

1. 2017-18
2. 2018-19
3. 2019-20
4. 2020-21
5. 2021-22
6. 2022-23
7. 2023-24
8. 2024-25
9. 2025-26

Choose season: 9

For visualization color, enter team name or a color code: Celtics

Accent color: #007A33
```

Bar Chart (option 4) follows a different order after it's selected: it asks for a stat, how many entities to show, season, and orientation, before finishing with the same accent color prompt.

Scatter Plot (option 5) follows a different order too: it asks for a first stat (Y axis), then a second stat (X axis), how many entities to show, and season, with no orientation and no color prompt at all (the chart uses player headshots or team logos, not a colored fill). Both stat prompts share the same categorized picker, with Bradley Analytics' own invented ratings listed first.

Animated Shot Chart (option 6) follows the exact same player/team and season flow as the Court Graphs above, just kept in its own category so it's not confused with the static charts.

The engine will automatically:

- Retrieve NBA data using the NBA API
- Process it for the selected visualization
- Generate the chart using Python and R
- Save the final PNG file (or GIF, for Animated Shot Chart)

Generated visualizations are saved in:

```
visualizations/
```

---

<a id="customization-section"></a>

## Customization

Every tunable value across every visualization: colors, sizes, shadow effects, minimum-attempts qualifiers, and more, all live in one file at the project root:

```
settings.json
```

Open it in any text editor, change a value, save, and run the engine again, no code changes needed. Settings are grouped by which visualization they affect (`shot_chart`, `heat_map`, `hex_shot_chart`, `animated_shot_chart`, `bar_chart`, `scatter_plot`), plus `bradley_ratings` for the formula behind every Bradley Analytics invented stat, and shared sections for colors, output dimensions, and data-fetching behavior (like `min_games_played`, which filters out small-sample-size players from Bar Chart and Scatter Plot leaderboards).

---

<a id="example-output-section"></a>

## Example Output

Example generated files:

```
visualizations/

jayson-tatum_2023-24_shot-chart.png
jayson-tatum_2023-24_heat-map-chart.png
jayson-tatum_2023-24_hex-shot-chart.png
top-10-bradley_3pt_rating_2025-26_bar-chart.png
top-10-bradley_3pt_rating-vs-3pa_2025-26_scatter-plot.png
jayson-tatum_2023-24_animated-shot-chart.gif
```

These visualizations can be used for:

- Player evaluation
- Scouting reports
- Social media analytics
- Basketball strategy discussions

---

<a id="troubleshooting-section"></a>

## Troubleshooting

### "Player not found"

Double check the spelling of the player's full name ("Jayson Tatum" not "J. Tatum" or a nickname). The lookup matches against the NBA's official player database, so only full, correctly spelled names will return a result.

### NBA API errors or timeouts

The engine pulls live data from the NBA API on every run. A failed request usually means the internet connection dropped or NBA.com is temporarily rate limiting requests. Wait a moment and try again.

### "Could not find Rscript" or R-related errors

Make sure R is installed and that `Rscript` is available from the command line (this works the same way on Windows and Mac). If you just installed R, restart your terminal so it picks up the updated PATH.

### Required R packages are missing

Open R and run:

```r
install.packages("tidyverse")
install.packages("ggplot2")
install.packages("hexbin")
install.packages("ggfx")
install.packages("ggimage")
install.packages("scales")
install.packages("jsonlite")
install.packages("gifski")
```

### bradley.bat won't run

`bradley.bat` is a Windows batch file, so it only runs on Windows. On Mac, run the Python script directly instead:

```bash
python3 python/bradley_analytics.py
```

### Visualization didn't save or file not found

Confirm you're looking in the `visualizations/` folder, and that the data retrieval and R visualization steps both completed without printing an error message.

---
