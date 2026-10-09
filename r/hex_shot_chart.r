library(tidyverse)
library(ggplot2)
library(hexbin)
library(ggfx)
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

# League-wide shots for the same season, downloaded by nba_data.py --
# used here to compute each hex's league-average FG% for comparison.
comparison_shots <- read_csv(
  "data/comparison_shots.csv",
  show_col_types = FALSE
)


filename <- request$filename[1]
width <- request$width[1]
height <- request$height[1]
team_colour <- request$color[1]


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file. court_xbnds/court_ybnds
# stay hardcoded here rather than in settings.json -- they're real
# NBA court measurements, not a style choice.
settings <- fromJSON("settings.json")
list2env(settings$hex_shot_chart, envir = environment())
below_avg_colour <- settings$colors$below_avg_colour

legend_box_ymin <- legend_y - legend_box_half_height
legend_box_ymax <- legend_y + legend_box_half_height

# Computed once, reused by both with_shadow() calls below, instead of
# repeating the same distance/angle-to-offset conversion twice.
shadow_x_offset <- shadow_distance * cos(shadow_angle * pi / 180)
shadow_y_offset <- shadow_distance * sin(shadow_angle * pi / 180)

court_xbnds <- c(-250, 250)
court_ybnds <- c(-60, 356.7)


# ---------------------------------------------------------------- Binning
# Bin both the player/team's shots and the league's shots into the
# same hex grid (identical xbins/xbnds/ybnds), so each hex's "cell" ID
# refers to the same physical hexagon in both datasets -- this is what
# makes them comparable.

shots <- shots |>
  mutate(
    LOC_X = as.numeric(LOC_X),
    LOC_Y = as.numeric(LOC_Y)
  ) |>
  filter(
    LOC_X >= court_xbnds[1], LOC_X <= court_xbnds[2],
    LOC_Y >= court_ybnds[1], LOC_Y <= court_ybnds[2]
  )

comparison_shots <- comparison_shots |>
  mutate(
    LOC_X = as.numeric(LOC_X),
    LOC_Y = as.numeric(LOC_Y)
  ) |>
  filter(
    LOC_X >= court_xbnds[1], LOC_X <= court_xbnds[2],
    LOC_Y >= court_ybnds[1], LOC_Y <= court_ybnds[2]
  )

subject_hb <- hexbin(
  shots$LOC_X, shots$LOC_Y,
  xbins = xbins,
  xbnds = court_xbnds,
  ybnds = court_ybnds,
  IDs = TRUE
)

league_hb <- hexbin(
  comparison_shots$LOC_X, comparison_shots$LOC_Y,
  xbins = xbins,
  xbnds = court_xbnds,
  ybnds = court_ybnds,
  IDs = TRUE
)

subject_centers <- hcell2xy(subject_hb)

subject_makes <- tapply(shots$SHOT_MADE_FLAG, subject_hb@cID, sum)
league_makes <- tapply(comparison_shots$SHOT_MADE_FLAG, league_hb@cID, sum)

subject_hex <- tibble(
  cell = subject_hb@cell,
  x = subject_centers$x,
  y = subject_centers$y,
  fga = subject_hb@count,
  fgm = as.numeric(subject_makes[as.character(subject_hb@cell)])
)

league_hex <- tibble(
  cell = league_hb@cell,
  league_fga = league_hb@count,
  league_fgm = as.numeric(league_makes[as.character(league_hb@cell)])
)


# ---------------------------------------------------------------- Combine
hex_data <- subject_hex |>
  left_join(league_hex, by = "cell") |>
  mutate(
    hex_id = row_number(),
    fg_pct = fgm / fga,
    league_fg_pct = league_fgm / league_fga,
    # How far this hex's FG% is from league average at that spot, in
    # percentage points. Safety fallback: if a hex genuinely has no
    # league shots to compare against (very unlikely with a full
    # season of league data), treat it as exactly at average (0)
    # rather than crash on NA.
    efficiency_diff = if_else(
      is.na(league_fg_pct),
      0,
      fg_pct - league_fg_pct
    ),
    # Normalize to 0-1 across +/- efficiency_saturation, clamped at
    # both ends -- 0 = full below_avg_colour, 1 = full team_colour,
    # 0.5 = exactly at league average.
    efficiency_t = pmin(pmax(
      (efficiency_diff + efficiency_saturation) / (2 * efficiency_saturation),
      0
    ), 1),
    size_factor = percent_rank(fga),
    radius = min_radius + (max_radius - min_radius) * size_factor
  ) |>
  # Draw order: biggest hexes first (back), smallest last (front), so
  # heavy overlap doesn't bury smaller hexes under bigger neighbors.
  arrange(desc(radius))

# Continuous color + opacity interpolation, driven by efficiency_t.
# Split out from the mutate() above because colorRamp() returns an
# RGB matrix, not a single value per row, so it doesn't fit inline as
# one mutate column.
efficiency_ramp <- colorRamp(c(below_avg_colour, team_colour))
hex_fill_rgb <- efficiency_ramp(hex_data$efficiency_t)

hex_data <- hex_data |>
  mutate(
    hex_fill = rgb(
      hex_fill_rgb[, 1], hex_fill_rgb[, 2], hex_fill_rgb[, 3],
      maxColorValue = 255
    ),
    hex_alpha = below_avg_alpha + (above_avg_alpha - below_avg_alpha) * efficiency_t
  )


# ---------------------------------------------------------------- Zone labels
# A curated set of 8 zones with fixed label positions -- not the NBA's
# full raw zone breakdown (SHOT_ZONE_BASIC x SHOT_ZONE_AREA has more
# combinations than that, which is what caused overlapping labels).
# Top, both wings, both mid-range/elbow areas, both corners, and the
# paint/restricted area combined -- matching a standard shot chart
# layout. zone_bucket() groups the NBA's own zone fields (already
# present in the data) down into these 8.

zone_bucket <- function(basic, area) {
  case_when(
    basic == "Above the Break 3" & area == "Center(C)" ~ "top_3",
    basic == "Above the Break 3" & area == "Left Side Center(LC)" ~ "left_wing_3",
    basic == "Above the Break 3" & area == "Right Side Center(RC)" ~ "right_wing_3",
    basic == "Left Corner 3" ~ "left_corner_3",
    basic == "Right Corner 3" ~ "right_corner_3",
    basic == "Mid-Range" & area %in% c("Left Side(L)", "Left Side Center(LC)") ~ "left_mid",
    basic == "Mid-Range" & area %in% c("Right Side(R)", "Right Side Center(RC)") ~ "right_mid",
    basic %in% c("Restricted Area", "In The Paint (Non-RA)") ~ "paint",
    basic == "Mid-Range" & area == "Center(C)" ~ "paint",
    TRUE ~ NA_character_
  )
}

# Fixed label positions -- tune any of these freely.
zone_positions <- tibble(
  zone = c(
    "top_3", "left_wing_3", "right_wing_3",
    "left_mid", "right_mid", "paint",
    "left_corner_3", "right_corner_3"
  ),
  label_x = c(0, -155, 155, -145, 145, 0, -240, 240),
  label_y = c(290, 230, 230, 110, 110, 40, 15, 15),
  label_hjust = c(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0, 1)
)

subject_zones <- shots |>
  mutate(zone = zone_bucket(SHOT_ZONE_BASIC, SHOT_ZONE_AREA)) |>
  filter(!is.na(zone)) |>
  group_by(zone) |>
  summarise(
    fga = n(),
    fgm = sum(SHOT_MADE_FLAG),
    .groups = "drop"
  )

league_zones <- comparison_shots |>
  mutate(zone = zone_bucket(SHOT_ZONE_BASIC, SHOT_ZONE_AREA)) |>
  filter(!is.na(zone)) |>
  group_by(zone) |>
  summarise(
    league_fga = n(),
    league_fgm = sum(SHOT_MADE_FLAG),
    .groups = "drop"
  )

zone_labels <- zone_positions |>
  left_join(subject_zones, by = "zone") |>
  left_join(league_zones, by = "zone") |>
  filter(!is.na(fga), fga >= min_zone_fga) |>
  mutate(
    fg_pct = fgm / fga,
    league_fg_pct = league_fgm / league_fga,
    label_text = sprintf(
      "%d/%d\n%.1f%% / %.1f%%",
      fgm, fga, fg_pct * 100, league_fg_pct * 100
    )
  )



# ---------------------------------------------------------------- Hexagon vertices
# Manually build each hex's 6 vertices at its own scaled radius --
# needed because hex size varies per-hex, which ggplot2's built-in
# geom_hex() doesn't support (it only draws uniformly-sized hexes).
hex_vertices <- function(cx, cy, radius, hex_id) {
  angles <- seq(30, 330, by = 60) * pi / 180
  tibble(
    hex_id = hex_id,
    x = cx + radius * cos(angles),
    y = cy + radius * sin(angles)
  )
}

hex_polygons <- map_dfr(
  seq_len(nrow(hex_data)),
  function(i) hex_vertices(
    hex_data$x[i],
    hex_data$y[i],
    hex_data$radius[i],
    hex_data$hex_id[i]
  )
)

hex_polygons <- hex_polygons |>
  left_join(
    select(hex_data, hex_id, hex_alpha, hex_fill),
    by = "hex_id"
  )


# ---------------------------------------------------------------- Legends
# Two small legends explaining the hex encoding: a 5-hex color/opacity
# ramp for FG% vs. league average, and a 5-hex size ramp for shot
# frequency (FGA). Built with the same hex_vertices() function used
# for the chart itself, so the swatches look identical to real hexes.
# Each framed in a white rounded-corner box.

color_alphas_all <- seq(below_avg_alpha, above_avg_alpha, length.out = 5)
color_alphas <- color_alphas_all[c(1, 3, 5)]

# Same gray-to-team-color ramp as the chart itself, so the legend's
# 3 swatches accurately preview what the actual hexes look like.
color_ramp <- colorRampPalette(c(below_avg_colour, team_colour))
color_fills_all <- color_ramp(5)
color_fills <- color_fills_all[c(1, 3, 5)]

color_legend <- tibble(
  position = 1:3,
  cx = color_legend_cx + (position - 2) * color_legend_spacing,
  cy = legend_y,
  radius = legend_hex_radius,
  alpha_val = color_alphas,
  fill_val = color_fills,
  legend_id = paste0("color_", position)
)

# Size legend uses variable spacing -- each gap is sized to the two
# neighboring hexes' actual radii plus a small buffer, not a fixed
# center-to-center distance. A fixed spacing would have to accommodate
# the two biggest hexes everywhere, wasting a lot of room between the
# smaller ones -- this keeps the whole row compact enough to fit its
# corridor.
size_radii_all <- seq(min_radius, max_radius, length.out = 5)
size_radii <- size_radii_all[c(2, 3, 4)]

size_cx_relative <- numeric(3)
for (i in 2:3) {
  size_cx_relative[i] <- size_cx_relative[i - 1] +
    size_radii[i - 1] + size_legend_gap + size_radii[i]
}
# Center the row on size_legend_cx
size_cx <- size_cx_relative - mean(range(size_cx_relative)) + size_legend_cx

size_legend <- tibble(
  position = 1:3,
  cx = size_cx,
  cy = legend_y,
  radius = size_radii,
  alpha_val = 1,
  fill_val = team_colour,
  legend_id = paste0("size_", position)
)

legend_hex_data <- bind_rows(color_legend, size_legend)

legend_polygons <- map_dfr(
  seq_len(nrow(legend_hex_data)),
  function(i) hex_vertices(
    legend_hex_data$cx[i],
    legend_hex_data$cy[i],
    legend_hex_data$radius[i],
    legend_hex_data$legend_id[i]
  )
) |>
  left_join(
    select(legend_hex_data, legend_id, alpha_val, fill_val),
    by = c("hex_id" = "legend_id")
  )

# "down FG%" / "up FG%" flank the color legend, same for FGA/size --
# positioned close to the outermost hex on each side. size_legend's
# cx and radius both increase together by construction, so the first
# row is the smallest/leftmost hex and the last row is the
# biggest/rightmost.
color_left_edge <- min(color_legend$cx) - legend_hex_radius
color_right_edge <- max(color_legend$cx) + legend_hex_radius
size_left_edge <- size_legend$cx[1] - size_legend$radius[1]
size_right_edge <- size_legend$cx[nrow(size_legend)] + size_legend$radius[nrow(size_legend)]

legend_labels <- tibble(
  x = c(
    color_left_edge - legend_text_gap,
    color_right_edge + legend_text_gap,
    size_left_edge - legend_text_gap,
    size_right_edge + legend_text_gap
  ),
  y = rep(legend_y, 4),
  label = c("\u2193 FG%", "\u2191 FG%", "\u2193 FGA", "\u2191 FGA"),
  label_hjust = c(1, 0, 1, 0)
)

# White rounded-corner boxes framing each legend, built manually as a
# polygon -- 4 quarter-circle arcs (one per corner) connected by
# straight edges, the same arc technique court.r already uses for the
# hoop and free-throw circle. Self-contained, no extra package needed.
rounded_rect_points <- function(xmin, xmax, ymin, ymax, radius, id, n_per_corner = 15) {
  make_corner <- function(cx, cy, start_deg, end_deg) {
    angles <- seq(start_deg, end_deg, length.out = n_per_corner) * pi / 180
    tibble(
      x = cx + radius * cos(angles),
      y = cy + radius * sin(angles)
    )
  }

  bind_rows(
    make_corner(xmax - radius, ymin + radius, -90, 0),   # bottom-right
    make_corner(xmax - radius, ymax - radius, 0, 90),    # top-right
    make_corner(xmin + radius, ymax - radius, 90, 180),  # top-left
    make_corner(xmin + radius, ymin + radius, 180, 270)  # bottom-left
  ) |>
    mutate(box_id = id)
}

legend_box_polygons <- bind_rows(
  rounded_rect_points(
    legend_box_xmin_left, legend_box_xmax_left,
    legend_box_ymin, legend_box_ymax,
    legend_box_corner_radius, "color"
  ),
  rounded_rect_points(
    legend_box_xmin_right, legend_box_xmax_right,
    legend_box_ymin, legend_box_ymax,
    legend_box_corner_radius, "size"
  )
)


# ---------------------------------------------------------------- Plot
# Drawn as two layers per hex: a filled layer whose color and opacity
# reflect above/below league average, then a separate fully-opaque
# white border layer on top -- so the border never fades even when
# the fill does.
hex_shot_chart <- ggplot() +
  geom_polygon(
    data = hex_polygons,
    aes(x, y, group = hex_id, alpha = hex_alpha, fill = hex_fill),
    color = NA
  ) +
  scale_alpha_identity() +
  scale_fill_identity() +
  geom_polygon(
    data = hex_polygons,
    aes(x, y, group = hex_id),
    fill = NA,
    color = "white",
    linewidth = 0.15
  ) +
  draw_court() +
  geom_polygon(
    data = legend_box_polygons,
    aes(x, y, group = box_id),
    fill = NA,
    color = "white",
    linewidth = 0.3
  ) +
  with_shadow(
    geom_text(
      data = zone_labels,
      aes(x = label_x, y = label_y, label = label_text, hjust = label_hjust),
      color = "white",
      fontface = "bold",
      size = zone_label_size,
      lineheight = 0.85
    ),
    colour = alpha("black", shadow_opacity),
    x_offset = shadow_x_offset,
    y_offset = shadow_y_offset,
    sigma = shadow_blur
  ) +
  geom_polygon(
    data = legend_polygons,
    aes(x, y, group = hex_id, alpha = alpha_val, fill = fill_val),
    color = NA
  ) +
  geom_polygon(
    data = legend_polygons,
    aes(x, y, group = hex_id),
    fill = NA,
    color = "white",
    linewidth = 0.15
  ) +
  with_shadow(
    geom_text(
      data = legend_labels,
      aes(x = x, y = y, label = label, hjust = label_hjust),
      color = "white",
      fontface = "bold",
      size = legend_text_size
    ),
    colour = alpha("black", shadow_opacity),
    x_offset = shadow_x_offset,
    y_offset = shadow_y_offset,
    sigma = shadow_blur
  ) +
  coord_fixed() +
  scale_x_continuous(
    limits = court_xbnds,
    expand = c(0, 0)
  ) +
  scale_y_continuous(
    limits = court_ybnds,
    expand = c(0, 0)
  ) +
  bradley_transparent_theme()


# Save final visualization
save_deliverable(
  hex_shot_chart,
  filename,
  "hex-shot-chart",
  width,
  height
)
