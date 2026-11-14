library(tidyverse)
library(ggplot2)
library(jsonlite)

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
team_colour <- request$color[1]
width <- request$width[1]
height <- request$height[1]


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
settings <- fromJSON("settings.json")
list2env(settings$heat_map, envir = environment())


# Creates a lighter version of the team color for lower shot density areas
lighten_color <- function(hex, amount = 0.15) {
  
  rgb_value <- grDevices::col2rgb(hex) / 255
  
  blended <- rgb_value + (1 - rgb_value) * amount
  
  grDevices::rgb(
    blended[1],
    blended[2],
    blended[3]
  )
}


# Create shot density heat map
heat_map <- ggplot(
  shots,
  aes(
    LOC_X,
    LOC_Y
  )
) +
  stat_density_2d(
    aes(
      fill = after_stat(density),
      alpha = after_stat(density)
    ),
    geom = "tile",
    contour = FALSE,
    n = grid_resolution,
    na.rm = TRUE
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
  scale_fill_gradientn(
    colours = c(
      lighten_color(team_colour),
      team_colour
    ),
    guide = "none"
  ) +
  scale_alpha_continuous(
    range = c(0, 5),
    guide = "none"
  ) +
  bradley_transparent_theme()


# Save final visualization
save_deliverable(
  heat_map,
  filename,
  "heat-map",
  width,
  height
)