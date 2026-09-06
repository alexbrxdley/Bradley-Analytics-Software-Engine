---
layout: page
title: Overview
sidebar: overview
---

<a id="overview-section"></a>

## Overview

The Bradley Analytics Software Engine is an NBA basketball analytics application that transforms raw player shooting data into professional quality basketball visualizations.

Built using Python, R, and NBA API data, this software engine lets users search by player or team, then generate court-based shot charts, stat-driven leaderboards and scatter plots (including Bradley Analytics' own invented player ratings), all rendered as polished, transparent, publication-ready visualizations.

The goal of this project is to combine data engineering, statistical visualization, and basketball storytelling into a simple analytics tool that converts complex NBA datasets into clear and meaningful insights.

This project is part of my basketball analytics portfolio, where I explore how data can be used to better understand player performance, team strategy, and decision making in professional sports.

### Why This Matters

NBA front offices, scouts, and media rely on visualizations like these to evaluate player tendencies and communicate performance in ways raw stat lines can't. This project demonstrates that same end-to-end analytics pipeline, from live API data through to a polished visual product, the same core workflow used in real sports analytics and business intelligence roles.

Portfolio:  
[Bradley Analytics Instagram](https://www.instagram.com/bradleyanalytics/)

---

<a id="features-section"></a>

## Features

### Automated NBA Data Collection

- Retrieves player shooting data directly from the NBA API
- Searches NBA players and available seasons automatically
- Processes player shot locations for analysis

### Shot Chart Generation

Creates customized shot charts displaying:

- Made and missed shots
- NBA court dimensions
- Player shooting locations
- Team specific color customization

### Shooting Heat Maps

Creates density based heat maps that visualize:

- High volume shooting areas
- Shot distribution tendencies
- Offensive strengths and weaknesses
- Team specific color customization

### Hex Shot Chart Generation

Creates hexagonal shot charts displaying:

- Shot frequency by hex size
- Shooting efficiency relative to league average by hex opacity
- Zone-by-zone breakdown with FGM/FGA and FG% vs. league FG%
- Team specific color customization

### Bar Chart Generation

Creates leaderboard-style bar charts displaying:

- Top N players or teams by any stat
- Player headshots or team logos in place of axis labels
- The value shown directly above each bar
- Vertical or horizontal orientation
- Team specific color customization

### Scatter Plot Generation

Creates two-stat comparison scatter plots displaying:

- Any two stats plotted against each other (Y axis vs. X axis)
- Player headshots or team logos in place of plot points
- Manually-included players or teams shown larger, so specific comparisons stand out
- Percentage-aware axis formatting on either axis independently

### Animated Shot Chart Generation

Creates an animated GIF of a player's or team's shots, revealed in true chronological game order:

- Made shots glow in team color and persist on screen permanently
- Missed shots draw in grey, hold briefly, then fade out and disappear
- A fixed-length GIF (default 15 seconds) regardless of shot volume, a full season's worth of shots reveal in batches to stay within that runtime
- Stylized curved shot trails, birds-eye view, matching the same court used by every other visualization

### Bradley Analytics Invented Stats

Custom 0-100 composite ratings, built from real NBA data rather than reverse-engineered from anything else, available as a stat source in both Bar Chart and Scatter Plot:

- **Bradley 3-Point Shooting Rating:** blends 3P% and 3-point volume (both weighted), combined across the current season and recent history, with smooth (not stepped) adjustments for one-off bad seasons and long-term shooting consistency
- Full formula and reasoning shown directly in the terminal stat picker
- More Bradley-invented ratings planned (see [Future Improvements](#future-improvements))

### Automated Visualization Pipeline

The engine manages the complete workflow:

1. User input
2. NBA data retrieval
3. Data processing
4. Visualization generation
5. Output creation

### Interactive Dashboard Sections

Beyond the core visualizations above, the Streamlit dashboard adds six
more sections, all built on the same live NBA API data:

- **Search by Criteria** -- filter the whole league by position,
  height, and any combination of stats or Bradley Ratings, capped at
  30 matching players, then generate a scatter plot of the result.
- **Trade Machine** -- swap players between two real rosters and see
  a before/after comparison, with optional user-entered salary figures
  for cap math (no licensed salary data is used).
- **On/Off Stats** -- pick a team and two or three teammates,
  and see how the team's per-48-minute stats shift with that specific
  group sharing the floor, compared to the team's season average.
- **Advanced Stats** -- true shooting %, usage rate,
  offensive/defensive rating, and more, for any player or team.
- **Community Visualizations** -- browse charts shared by other users
  of the dashboard, or share your own from any of the sections above.
- **Glossary** -- every stat abbreviation used throughout the
  dashboard, defined in one place.

---

<a id="how-it-works-section"></a>

## How It Works

### Architecture Diagram

```
           User Input
                |
                v
+-------------------------------+
| Bradley Analytics Engine      |
| Python Application            |
+-------------------------------+
                |
                v
     NBA API Data Retrieval
                |
                v
+-------------------------------+
| Data Processing               |
| pandas + CSV Storage          |
+-------------------------------+
                |
                v
   Shot Data  or  Stat Leaderboard
   (court graphs)  (Bar Chart / Scatter Plot,
                    including Bradley Analytics'
                    own invented ratings)
                |
                v
+-------------------------------+
| R Visualization Engine        |
| ggplot2 + Custom NBA Court    |
+-------------------------------+
                |
                v
+-------------------------------+
| Generated Visualizations      |
+-------------------------------+
```

### Workflow

```
1. User searches by player or team
                |
                v
2. User chooses a visualization
                |
                v
3. Python retrieves NBA data
   (shot-level data for court graphs,
    season leaderboards for Bar Chart/Scatter Plot)
                |
                v
4. Data is cleaned and organized
                |
                v
5. R creates the visualization
                |
                v
6. Final PNG (or GIF, for Animated Shot Chart) is saved
```

---

<a id="technologies-used-section"></a>

## Technologies Used

### Programming Languages

- Python
- R

### Data Collection

- NBA API
- pandas

### Visualization

- ggplot2
- tidyverse
- hexbin
- ggfx
- ggimage
- scales
- jsonlite
- gifski

### Development Tools

- Visual Studio Code
- Git/GitHub

### Analytics Skills Applied

- Data collection
- Data cleaning
- Statistical visualization
- Sports analytics storytelling
- Basketball performance analysis

---

<a id="project-structure-section"></a>

## Project Structure

```
Bradley Analytics Software Engine/

│
├── data/
│   └── Generated NBA datasets
│
├── visualizations/
│   └── Generated visualizations
│
├── python/
│   ├── bradley_analytics.py
│   ├── nba_data.py
│   ├── axis_data.py
│   ├── scatter_data.py
│   └── bradley_ratings.py
│
├── r/
│   ├── shot_chart.r
│   ├── heat_map.r
│   ├── hex_shot_chart.r
│   ├── animated_shot_chart.r
│   ├── bar_chart.r
│   ├── scatter_plot.r
│   └── functions/
│       ├── court.r
│       └── save_plot.r
|
├── reports/
│   └── Bradley Analytics reports
│
├── assets/
│   └── README images and banner
|
├── README.md
├── LICENSE
├── requirements.txt
├── settings.json
└── bradley.bat
```

---
