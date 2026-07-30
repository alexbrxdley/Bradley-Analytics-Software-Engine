library(tidyverse)
library(ggplot2)

source("r/functions/court.r")
source("r/functions/save_plot.r")


# Load project data
request <- read_csv(
  "data/request.csv",
  show_col_types = FALSE
)

shots <- read_csv(
  "data/shots.csv",
  show_col_types = FALSE
)


filename <- request$filename[1]
width <- request$width[1]
height <- request$height[1]
team_colour <- request$color[1]


# Identify made and missed shots
shots <- shots |>
  mutate(
    LOC_X = as.numeric(LOC_X),
    LOC_Y = as.numeric(LOC_Y),
    Shot_Result = if_else(
      SHOT_MADE_FLAG == 1,
      "Made",
      "Missed"
    )
  )


# Create shot chart
shot_chart <- ggplot(
  shots,
  aes(
    LOC_X,
    LOC_Y
  )
) +
  geom_point(
    data = filter(
      shots,
      Shot_Result == "Missed"
    ),
    color = "#9A9A9A",
    alpha = 0.75,
    size = 1.4
  ) +
  geom_point(
    data = filter(
      shots,
      Shot_Result == "Made"
    ),
    color = team_colour,
    alpha = 1,
    size = 1.4
  ) +
  draw_court() +
  coord_fixed() +
  scale_x_continuous(
    limits = c(-250, 250),
    expand = c(0, 0)
  ) +
  scale_y_continuous(
    limits = c(-60, 356.7),
    expand = c(0, 0)
  ) +
  bradley_transparent_theme()


# Save final visualization
save_deliverable(
  shot_chart,
  filename,
  "shot-chart",
  width,
  height
)


print(shot_chart)