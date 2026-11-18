library(tidyverse)
library(ggplot2)
library(ggfx)
library(gifski)
library(jsonlite)

source("r/functions/court.r")


# Load project data
request <- read_csv(
  "data/request.csv",
  show_col_types = FALSE
)

shots <- read_csv(
  "data/shots.csv",
  show_col_types = FALSE
)

if (nrow(shots) == 0) {
  stop("shots.csv has no rows -- nba_data.py may not have downloaded any shots for this player/season.")
}


filename <- request$filename[1]
width <- request$width[1]
height <- request$height[1]
team_colour <- request$color[1]


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
settings <- fromJSON("settings.json")
list2env(settings$animated_shot_chart, envir = environment())
missed_colour <- settings$colors$missed_shot_colour
export_dpi <- settings$dimensions$export_dpi


# ---------------------------------------------------------------- Chronological order
# GAME_DATE orders shots across games; PERIOD then time remaining
# (descending, since NBA clocks count down) orders shots within a
# single game. All five columns come straight from ShotChartDetail's
# own response -- nba_data.py already saves the full raw response, so
# nothing upstream needed to change to get these.
shots <- shots |>
  mutate(
    LOC_X = as.numeric(LOC_X),
    LOC_Y = as.numeric(LOC_Y),
    is_made = SHOT_MADE_FLAG == 1,
    clock_seconds = MINUTES_REMAINING * 60 + SECONDS_REMAINING
  ) |>
  # Rare backcourt/full-court heaves (typically end-of-quarter
  # buzzer-beaters) sit far outside normal shooting range and can push
  # the curve's control point way past any reasonable plot boundary --
  # excluded here rather than risk clipping, since they're not
  # representative shots for a real chart anyway.
  filter(abs(LOC_X) <= 250, LOC_Y <= 350) |>
  arrange(GAME_DATE, PERIOD, desc(clock_seconds)) |>
  mutate(shot_index = row_number())

if (nrow(shots) == 0) {
  stop("Every shot was filtered out by the LOC_X/LOC_Y range check -- check that shots.csv has real coordinate data, not just backcourt heaves.")
}

total_shots <- nrow(shots)


# ---------------------------------------------------------------- Frame/batch timing
# A fixed frame budget (independent of shot count) is what keeps the
# GIF capped at max_seconds regardless of whether this is a 50-shot
# stretch or an 800-shot season -- shots_per_batch scales up instead,
# so a high-volume player shows several shots revealing at once rather
# than the animation running long.
total_frames <- round(fps * max_seconds)
hold_frames <- round(fps * hold_seconds)
reveal_frames <- total_frames - hold_frames
num_batches <- max(1, reveal_frames %/% frames_per_batch)
shots_per_batch <- ceiling(total_shots / num_batches)

shots <- shots |>
  mutate(batch = pmin(ceiling(shot_index / shots_per_batch), num_batches))


# ---------------------------------------------------------------- Arc geometry
# A stylized curved path from the shot location to the hoop (0, 0) --
# not a literal shot trajectory (this is a top-down court view, a real
# shot's arc is vertical and wouldn't read as a curve from directly
# above). A quadratic Bezier curve pushed radially outward from the
# hoop gives every shot the same "bows away from the basket" look,
# regardless of which side of the court it's on -- strength scales
# with how far off-center the shot is (corner shots bow the most, a
# shot from straight up the middle comes in nearly straight).
bezier_arc <- function(x0, y0, n = arc_points_per_shot) {
  x1 <- 0
  y1 <- 0

  # court_half_width matches court_xbnds used elsewhere in the
  # project (-250 to 250).
  court_half_width <- 250
  bow_amount <- arc_bow_amount * (abs(x0) / court_half_width)

  # Direction from the hoop out to the shot -- pushing the control
  # point further out along this same direction always bows the curve
  # away from the basket, never side to side, for every shot alike.
  dist_from_hoop <- sqrt(x0^2 + y0^2)
  out_x <- if (dist_from_hoop == 0) 0 else x0 / dist_from_hoop
  out_y <- if (dist_from_hoop == 0) 0 else y0 / dist_from_hoop

  mid_x <- (x0 + x1) / 2
  mid_y <- (y0 + y1) / 2
  ctrl_x <- mid_x + out_x * bow_amount
  ctrl_y <- mid_y + out_y * bow_amount

  t <- seq(0, 1, length.out = n)

  tibble(
    x = (1 - t)^2 * x0 + 2 * (1 - t) * t * ctrl_x + t^2 * x1,
    y = (1 - t)^2 * y0 + 2 * (1 - t) * t * ctrl_y + t^2 * y1,
    point_order = seq_len(n)
  )
}

# Precomputed once per shot, not regenerated per frame -- the frame
# loop below only ever slices/filters this, keeping rendering fast
# even at hundreds of shots across 180 frames.
arc_paths <- pmap_dfr(
  list(shots$shot_index, shots$LOC_X, shots$LOC_Y, shots$is_made, shots$batch),
  function(idx, x0, y0, made, b) {
    arc <- bezier_arc(x0, y0)
    arc$shot_index <- idx
    arc$is_made <- made
    arc$batch <- b
    arc
  }
)

# ---------------------------------------------------------------- Per-frame state
# Every shot's current reveal fraction (how much of its arc is drawn
# so far) and opacity (how visible it currently is), as a function of
# frame number -- dots ramp in and persist forever for both made and
# missed shots, matching the static shot chart where every attempt
# leaves a permanent marker. Arcs cap at line_max_opacity; made arcs
# persist at that cap forever, missed arcs hold briefly then fade to
# 0 and disappear -- only the trail vanishes, not the shot marker.
shot_state_at_frame <- function(f) {
  arc_paths |>
    mutate(
      batch_start = (batch - 1) * frames_per_batch + 1,
      batch_end = batch * frames_per_batch,
      progress = pmin(pmax((f - batch_start + 1) / frames_per_batch, 0), 1),
      fade_end = batch_end + frames_per_batch,
      # Dot appears instantly the moment its batch starts (not a
      # gradual ramp like the arc) and then persists forever -- the
      # marker shows up first, then the arc draws in from it.
      dot_opacity = if_else(f >= batch_start, 1, 0),
      line_opacity = case_when(
        is_made ~ line_max_opacity * progress,
        f <= batch_end ~ line_max_opacity * progress,
        f <= fade_end ~ line_max_opacity * (1 - ((f - batch_end) / frames_per_batch)),
        TRUE ~ 0
      ),
      opacity = dot_opacity,
      reveal_fraction = progress
    ) |>
    filter(opacity > 0) |>
    group_by(shot_index) |>
    filter(point_order <= ceiling(first(reveal_fraction) * arc_points_per_shot)) |>
    ungroup() |>
    arrange(shot_index, point_order)
}

build_frame_plot <- function(f) {
  frame_data <- shot_state_at_frame(f)

  made_data <- frame_data |> filter(is_made)
  missed_data <- frame_data |> filter(!is_made)

  p <- ggplot() +
    draw_court(color = "white", lw = 0.6)

  if (nrow(missed_data) > 0) {
    p <- p +
      geom_path(
        data = missed_data,
        aes(x, y, group = shot_index, alpha = line_opacity),
        color = missed_colour,
        linewidth = arc_linewidth
      ) +
      geom_point(
        data = missed_data |> group_by(shot_index) |> filter(point_order == min(point_order)) |> ungroup(),
        aes(x, y, alpha = opacity),
        color = missed_dot_colour,
        size = dot_size
      )
  }

  if (nrow(made_data) > 0) {
    p <- p +
      with_outer_glow(
        geom_path(
          data = made_data,
          aes(x, y, group = shot_index, alpha = line_opacity),
          color = team_colour,
          linewidth = arc_linewidth
        ),
        colour = team_colour,
        sigma = glow_sigma,
        expand = glow_expand
      ) +
      geom_point(
        data = made_data |> group_by(shot_index) |> filter(point_order == min(point_order)) |> ungroup(),
        aes(x, y, alpha = opacity),
        color = team_colour,
        size = dot_size
      )
  }

  p +
    scale_alpha_identity() +
    coord_fixed() +
    xlim(plot_xlim) +
    ylim(plot_ylim) +
    theme_void() +
    theme(
      legend.position = "none",
      plot.background = element_rect(fill = background_colour, color = NA),
      panel.background = element_rect(fill = background_colour, color = NA)
    )
}


# ---------------------------------------------------------------- Render
dir.create("visualizations", showWarnings = FALSE)

output_path <- file.path("visualizations", paste0(filename, "_animated-shot-chart.gif"))

save_gif(
  {
    for (f in seq_len(total_frames)) {
      reveal_frame <- min(f, reveal_frames)
      print(build_frame_plot(reveal_frame))
    }
  },
  gif_file = output_path,
  width = width * export_dpi,
  height = height * export_dpi,
  res = export_dpi,
  delay = 1 / fps,
  bg = background_colour
)

print(paste0("Saved: ", output_path))
