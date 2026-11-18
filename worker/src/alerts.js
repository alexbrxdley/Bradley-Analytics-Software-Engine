// The alert rules are shared with the website: docs/assets/alert-rules.js (wrangler bundles it into the Worker), so the
// alerts sent while the site is closed are exactly the ones the site shows while it's open.
import "../../docs/assets/alert-rules.js";
const R = globalThis.BAAlerts;
export const { KINDS, TEAMS, detect, detectNews, detectHighlights, due, recapFor, reminder, allowed, pictureFor, gameDay } = R;
