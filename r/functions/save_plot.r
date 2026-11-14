# save_plot.R
#
# Shared functions used by all visualizations.
# Creates a transparent theme and saves charts to visualizations/.

# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
library(jsonlite)
settings <- fromJSON("settings.json")
export_dpi <- settings$dimensions$export_dpi

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
    dpi = export_dpi,
    bg = "transparent"
  )
  
  cat("Saved:", normalizePath(output_path), "\n")
  
  invisible(output_path)
}