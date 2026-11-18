library(tidyverse)
library(ggplot2)
library(ggfx)
library(ggimage)
library(scales)
library(jsonlite)

source("r/functions/save_plot.r")


# Load project data
request <- read_csv(
  "data/axis_request.csv",
  show_col_types = FALSE
)

axis_data <- read_csv(
  "data/axis_data.csv",
  show_col_types = FALSE
)


filename <- request$filename[1]
width <- request$width[1]
height <- request$height[1]
team_colour <- request$color[1]
stat_field <- request$stat_field[1]
stat_display_name <- request$stat_display_name[1]
stat_source <- request$stat_source[1]
orientation <- request$orientation[1]
top_n <- request$top_n[1]
season <- request$season[1]
mode <- request$mode[1]


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
settings <- fromJSON("settings.json")
list2env(settings$bar_chart, envir = environment())
neutral_colour <- settings$colors$neutral_colour

# Computed once, matching the same pattern used in hex_shot_chart.r.
shadow_x_offset <- shadow_distance * cos(shadow_angle * pi / 180)
shadow_y_offset <- shadow_distance * sin(shadow_angle * pi / 180)


# ---------------------------------------------------------------- Y-axis title
# "Top N [stat] per game leaders [season]", plus a second line listing
# any manually-included names, if there are any. stat_display_name is
# computed in bradley_analytics.py (STAT_DISPLAY_NAMES) -- common
# short stats keep their abbreviation (FGA, TS%), everything else
# reads as a natural name (points, blocks), and Bradley Analytics'
# own stats get Title Case.

included_names_raw <- request$included_names[1]

included_names <- if (!is.na(included_names_raw) && included_names_raw != "") {
  str_split(included_names_raw, "\\|")[[1]]
} else {
  character(0)
}

per_game_phrase <- if (stat_source %in% c("bio", "bradley_rating")) "" else " per game"

y_title <- paste0("Top ", top_n, " ", stat_display_name, per_game_phrase, " leaders ", season)

if (length(included_names) > 0) {
  y_title <- paste0(
    y_title, "\n",
    "(Includes ", paste(included_names, collapse = ", "), ")"
  )
}

# Extra blank line for spacing between the title and the tick numbers
y_title <- paste0(y_title, "\n")


# ---------------------------------------------------------------- Bar colors
# Specifically-requested entities get the accent color, everyone else
# gets a neutral gray. If no specific entities were requested,
# axis_data.py already set is_included to TRUE for every row, so every
# bar gets the accent color.
axis_data <- axis_data |>
  mutate(
    bar_colour = if_else(is_included, team_colour, neutral_colour),
    name = fct_reorder(name, value),
    # First name on one line, last name on the next -- only used if
    # this ends up on the text-label fallback path below.
    display_label = str_replace(as.character(name), " ", "\n")
  )


# ---------------------------------------------------------------- X-axis: images or text
# Player mode gets each player's official NBA.com headshot (PNG).
# Team mode gets each team's logo from ESPN's CDN (also PNG) --
# NBA.com's own logo CDN only serves SVG, which needs extra local
# rendering support this may not have, so ESPN's PNG source is used
# instead for reliability, matching the player headshots' format.
# Both keyed off entity_id (player_id, or an ESPN team abbreviation
# for team mode), already resolved by axis_data.py. Falls back to the
# shadowed text-label approach only if entity_id is somehow missing.
has_images <- !any(is.na(axis_data$entity_id) | axis_data$entity_id == "")

if (has_images) {
  axis_data <- axis_data |>
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

  label_y_position <- -max(axis_data$value) * 0.08
} else {
  label_y_position <- -max(axis_data$value) * 0.05
}


# ---------------------------------------------------------------- Y-axis breaks/labels
# The bottom expansion (added for headshot/label clearance below the
# bars) pushes the visible axis range below the real data -- without
# this, ggplot2's automatic tick placement puts a meaningless negative
# tick (e.g. -0.25%) in that empty space. Computing breaks from the
# real data range (0 to max value) instead avoids that, regardless of
# how much clearance the expansion below adds.
is_percentage_stat <- str_detect(stat_field, "_PCT$")

y_breaks <- scales::breaks_pretty(n = 5)(c(0, max(axis_data$value)))
y_breaks <- y_breaks[y_breaks >= 0]

y_labels <- if (is_percentage_stat) {
  scales::percent(y_breaks, accuracy = 1)
} else {
  scales::comma(y_breaks)
}

# Value shown above each bar -- same percentage formatting as the
# y-axis for percentage stats, whole numbers otherwise (e.g. a 0-100
# rating shows as "90", not "90.3").
axis_data <- axis_data |>
  mutate(
    value_label = if (is_percentage_stat) {
      scales::percent(value, accuracy = 1)
    } else {
      scales::comma(round(value))
    },
    value_label_y = value + max(axis_data$value) * value_label_gap
  )


# ---------------------------------------------------------------- Plot
bar_chart <- ggplot(
  axis_data,
  aes(x = name, y = value, fill = bar_colour)
) +
  geom_col(color = bar_border_colour, linewidth = bar_border_width) +
  scale_fill_identity()

if (has_images) {
  bar_chart <- bar_chart +
    geom_image(
      aes(x = name, y = label_y_position, image = image_url),
      size = image_size,
      # Off by default this fetches fresh every time instead of
      # potentially showing an out-of-date cached copy from an
      # earlier run (e.g. a player's photo before a trade).
      use_cache = FALSE
    )
} else {
  bar_chart <- bar_chart +
    with_shadow(
      geom_text(
        aes(x = name, y = label_y_position, label = display_label),
        color = "white",
        family = "Arial",
        fontface = "bold",
        size = x_label_size,
        angle = x_label_angle,
        hjust = 1
      ),
      colour = alpha("black", shadow_opacity),
      x_offset = shadow_x_offset,
      y_offset = shadow_y_offset,
      sigma = shadow_blur
    )
}

bar_chart <- bar_chart +
  with_shadow(
    geom_text(
      data = axis_data,
      aes(x = name, y = value_label_y, label = value_label),
      color = "white",
      family = "Arial",
      fontface = "bold",
      size = value_label_size,
      vjust = 0
    ),
    colour = alpha("black", shadow_opacity),
    x_offset = shadow_x_offset,
    y_offset = shadow_y_offset,
    sigma = shadow_blur
  ) +
  labs(x = NULL, y = y_title) +
  scale_y_continuous(
    expand = expansion(mult = c(0.2, 0.12)),
    breaks = y_breaks,
    labels = y_labels
  ) +
  bradley_transparent_theme() +
  theme(
    axis.text.x = element_blank(),
    axis.ticks.x = element_blank(),
    axis.text.y = element_text(
      color = "white", family = "Arial", fontface = "bold", size = 12
    ),
    axis.title.y = element_text(
      color = "white", family = "Arial", fontface = "bold",
      size = 13, angle = 90, lineheight = 1.1
    )
  )

if (orientation == "horizontal") {
  bar_chart <- bar_chart + coord_flip()
}


# Save final visualization
save_deliverable(
  bar_chart,
  filename,
  "bar-chart",
  width,
  height
)
