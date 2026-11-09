# Reference values for pipeline/tests/test_detection.py (Moving Epidemic Method).
# Run in any R with the CRAN `mem` package (validated with mem 2.19, R 4.4.2), e.g.
#   docker run --rm -v "$PWD:/w" rocker/r-ver:4.4.2 sh -c \
#     'Rscript -e "install.packages(\"mem\", repos=\"https://cloud.r-project.org\")" &&
#      Rscript /w/scripts/validate_mem.R /w/pipeline/tests/data/mem_flucyl.csv'
# Prints: epidemic threshold, post-epidemic threshold, medium, high, very high intensity,
# then each season's epidemic start and end (1-based weeks), all with memmodel() defaults.
library(mem)
for (f in commandArgs(trailingOnly = TRUE)) {
  d <- read.csv(f, row.names = 1, check.names = FALSE)
  m <- memmodel(d)
  cat(basename(f), sprintf("%.10f", c(m$epidemic.thresholds, m$intensity.thresholds)), "\n")
  cat("start", unlist(m$real.length.data[4, ]), "\n")
  cat("end", unlist(m$real.length.data[5, ]), "\n")
}
