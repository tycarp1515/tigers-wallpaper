// Tigers schedule widget for Scriptable
//
// Widget Parameter controls which image loads:
//    (blank)  -> widget-next.png    next 4 games      [use size: Medium]
//    month    -> widget-month.png   month in play     [use size: Large]
//    july     -> widget-july.png    a specific month  [use size: Large]
//    august, september, ...
//
const USER = "tycarp1515"
const REPO = "tigers-wallpaper"

let p = (args.widgetParameter || "next").toLowerCase().trim()
let file = (p === "next") ? "widget-next.png" : `widget-${p}.png`
let url = `https://raw.githubusercontent.com/${USER}/${REPO}/main/output/${file}`

let w = new ListWidget()
w.setPadding(0, 0, 0, 0)

try {
  let req = new Request(url)
  req.headers = { "Cache-Control": "no-cache" }
  w.backgroundImage = await req.loadImage()
} catch (e) {
  w.backgroundColor = new Color("#0c2340")
  let t = w.addText("Tigers schedule\nunavailable")
  t.textColor = Color.white()
  t.font = Font.mediumSystemFont(14)
  t.centerAlignText()
}

// Ask iOS to refresh in ~1 hour (iOS decides the real timing).
w.refreshAfterDate = new Date(Date.now() + 60 * 60 * 1000)
// Tap opens the image full size.
w.url = url

if (config.runsInWidget) {
  Script.setWidget(w)
} else {
  await w.presentMedium()
}
Script.complete()
