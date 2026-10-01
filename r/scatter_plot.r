library(tidyverse)
library(ggplot2)
library(ggfx)
library(ggimage)
library(scales)
library(jsonlite)

source("r/functions/save_plot.r")


# Load project data
request <- read_csv(
  "data/scatter_request.csv",
  show_col_types = FALSE
)

scatter_data <- read_csv(
  "data/scatter_data.csv",
  show_col_types = FALSE
)


filename <- request$filename[1]
width <- request$width[1]
height <- request$height[1]
stat_field_y <- request$stat_field_y[1]
stat_display_name_y <- request$stat_display_name_y[1]
stat_field_x <- request$stat_field_x[1]
stat_display_name_x <- request$stat_display_name_x[1]
mode <- request$mode[1]


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
settings <- fromJSON("settings.json")
list2env(settings$scatter_plot, envir = environment())
neutral_colour <- settings$colors$neutral_colour
# No color prompt happens for Scatter Plot (nothing on this chart
# visually uses one) -- this only matters for the rare text-label
# fallback below, so a fixed default is used instead of asking.
team_colour <- settings$colors$default_color

# Computed once, same pattern used in bar_chart.r/hex_shot_chart.r.
shadow_x_offset <- shadow_distance * cos(shadow_angle * pi / 180)
shadow_y_offset <- shadow_distance * sin(shadow_angle * pi / 180)


scatter_data <- scatter_data |>
  mutate(
    point_colour = if_else(is_included, team_colour, neutral_colour),
    point_size = if_else(is_included, image_size * highlighted_image_size_multiplier, image_size),
    display_label = str_replace(as.character(name), " ", "\n")
  )


# ---------------------------------------------------------------- Images or text
# Same CDN sources and fallback logic as bar_chart.r: player headshots
# from NBA.com, team logos from ESPN (NBA.com's own team logo CDN only
# serves SVG, which needs extra local rendering support this may not
# have). Falls back to shadowed text labels only if entity_id is
# somehow missing.
has_images <- !any(is.na(scatter_data$entity_id) | scatter_data$entity_id == "")

if (has_images) {
  scatter_data <- scatter_data |>
    mutate(
      image_url = if (mode == "player") {
        paste0(
          "https://cdn.nba.com/headshots/nba/latest/1040x760/",
          entity_id, ".png"
        )
      } else {
        paste0(
          "https://a.espncdn.com/i/teamlogos/nba/500/",
          entity_id, ".png"
        )
      }
    )
}


# ---------------------------------------------------------------- Axis formatting
# Percentage-aware for either axis independently -- either one could
# be a percentage stat regardless of what the other is.
is_percentage_y <- str_detect(stat_field_y, "_PCT$")
is_percentage_x <- str_detect(stat_field_x, "_PCT$")

y_breaks <- scales::breaks_pretty(n = 5)(range(scatter_data$y_value))
y_labels <- if (is_percentage_y) scales::percent(y_breaks, accuracy = 1) else scales::comma(y_breaks)

x_breaks <- scales::breaks_pretty(n = 5)(range(scatter_data$x_value))
x_labels <- if (is_percentage_x) scales::percent(x_breaks, accuracy = 1) else scales::comma(x_breaks)

# Axis titles: capitalize only if the display name currently starts
# lowercase ("assists" -> "Assists") -- leaves anything already
# correctly cased alone ("FGA", "TS%", "Bradley 3-Point Rating").
capitalize_first <- function(s) {
  if (str_detect(str_sub(s, 1, 1), "[a-z]")) {
    paste0(str_to_upper(str_sub(s, 1, 1)), str_sub(s, 2))
  } else {
    s
  }
}

y_title <- capitalize_first(stat_display_name_y)
x_title <- capitalize_first(stat_display_name_x)


# ---------------------------------------------------------------- Plot
scatter_plot <- ggplot(
  scatter_data,
  aes(x = x_value, y = y_value)
)

if (has_images) {
  scatter_plot <- scatter_plot +
    geom_image(
      aes(image = image_url, size = I(point_size)),
      # Off by default this fetches fresh every time instead of
      # potentially showing an out-of-date cached copy from an
      # earlier run (e.g. a player's photo before a trade).
      use_cache = FALSE
    )
} else {
  scatter_plot <- scatter_plot +
    with_shadow(
      geom_text(
        aes(label = display_label, color = point_colour),
        family = "Arial",
        fontface = "bold",
        size = text_label_size
      ),
      colour = alpha("black", shadow_opacity),
      x_offset = shadow_x_offset,
      y_offset = shadow_y_offset,
      sigma = shadow_blur
    ) +
    scale_color_identity()
}

scatter_plot <- scatter_plot +
  labs(x = x_title, y = y_title) +
  scale_x_continuous(
    expand = expansion(mult = axis_expand),
    breaks = x_breaks,
    labels = x_labels
  ) +
  scale_y_continuous(
    expand = expansion(mult = axis_expand),
    breaks = y_breaks,
    labels = y_labels
  ) +
  bradley_transparent_theme() +
  theme(
    axis.text.x = element_text(
      color = "white", family = "Arial", fontface = "bold", size = 12
    ),
    axis.text.y = element_text(
      color = "white", family = "Arial", fontface = "bold", size = 12
    ),
    axis.title.x = element_text(
      color = "white", family = "Arial", fontface = "bold", size = 13,
      margin = margin(t = axis_title_margin)
    ),
    axis.title.y = element_text(
      color = "white", family = "Arial", fontface = "bold",
      size = 13, angle = 90, lineheight = 1.1,
      margin = margin(r = axis_title_margin)
    )
  )

save_deliverable(
  scatter_plot,
  filename,
  "scatter-plot",
  width,
  height
)
