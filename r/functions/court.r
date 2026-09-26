# court.R
# Draws the NBA half court using nba_api shot coordinates

arc_points <- function(cx, cy, radius, start_deg, end_deg, n = 100) {
  
  angles <- seq(
    start_deg,
    end_deg,
    length.out = n
  ) * pi / 180
  
  data.frame(
    x = cx + radius * cos(angles),
    y = cy + radius * sin(angles)
  )
}


draw_court <- function(color = "white", lw = 0.6) {
  
  list(
    
    # Hoop
    geom_path(
      data = arc_points(0, 0, 7.5, 0, 360),
      aes(x, y),
      inherit.aes = FALSE,
      color = color,
      linewidth = lw
    ),
    
    # Backboard
    annotate(
      "segment",
      x = -30,
      xend = 30,
      y = -7.5,
      yend = -7.5,
      color = color,
      linewidth = lw
    ),
    
    # Paint
    annotate(
      "rect",
      xmin = -80,
      xmax = 80,
      ymin = -47.5,
      ymax = 142.5,
      fill = NA,
      color = color,
      linewidth = lw
    ),
    
    # Free throw circle
    geom_path(
      data = arc_points(0, 142.5, 60, 0, 180),
      aes(x, y),
      inherit.aes = FALSE,
      color = color,
      linewidth = lw
    ),
    
    geom_path(
      data = arc_points(0, 142.5, 60, 180, 360),
      aes(x, y),
      inherit.aes = FALSE,
      color = color,
      linewidth = lw,
      linetype = "dashed"
    ),
    
    # Restricted area
    geom_path(
      data = arc_points(0, 0, 40, 0, 180),
      aes(x, y),
      inherit.aes = FALSE,
      color = color,
      linewidth = lw
    ),
    
    # Corner three lines
    annotate(
      "segment",
      x = -220,
      xend = -220,
      y = -47.5,
      yend = 92.5,
      color = color,
      linewidth = lw
    ),
    
    annotate(
      "segment",
      x = 220,
      xend = 220,
      y = -47.5,
      yend = 92.5,
      color = color,
      linewidth = lw
    ),
    
    # Three point arc
    geom_path(
      data = arc_points(0, 0, 237.5, 22, 158),
      aes(x, y),
      inherit.aes = FALSE,
      color = color,
      linewidth = lw
    )
  )
}