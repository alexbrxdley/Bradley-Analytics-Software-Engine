# save_plot.R
#
# Shared functions used by all visualizations.
# Creates a transparent theme and saves charts to visualizations/.

bradley_transparent_theme <- function() {
  
  theme_void() +
    theme(
      legend.position = "none",
      plot.background = element_rect(
        fill = "transparent",
        color = NA
      ),
      panel.background = element_rect(
        fill = "transparent",
        color = NA
      )
    )
}


# Saves PNG visualizations with a consistent filename.
save_deliverable <- function(plot, filename, suffix, width, height) {
  
  dir.create(
    "visualizations",
    showWarnings = FALSE
  )
  
  output_path <- file.path(
    "visualizations",
    paste0(filename, "_", suffix, ".png")
  )
  
  ggsave(
    filename = output_path,
    plot = plot,
    width = width,
    height = height,
    dpi = 300,
    bg = "transparent"
  )
  
  cat("Saved:", normalizePath(output_path), "\n")
  
  invisible(output_path)
}


# Saves animated visualizations as GIF files.
save_animated_deliverable <- function(
    plot,
    filename,
    suffix,
    width,
    height,
    nframes = 200,
    fps = 24
) {
  
  dir.create(
    "visualizations",
    showWarnings = FALSE
  )
  
  output_path <- file.path(
    "visualizations",
    paste0(filename, "_", suffix, ".gif")
  )
  
  animate(
    plot,
    width = width * 300,
    height = height * 300,
    units = "px",
    fps = fps,
    nframes = nframes,
    renderer = gifski_renderer(output_path)
  )
  
  cat("Saved:", normalizePath(output_path), "\n")
  
  invisible(output_path)
}