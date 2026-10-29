// Turns demo/session.json (real output captured by demo/record.py) into an MP4.
// Usage: swift demo/render.swift demo/session.json demo/winddown-demo.mp4
import AVFoundation
import CoreText
import Foundation

let W = 1280, H = 720, FPS: Int32 = 30
let args = CommandLine.arguments
let session = try! JSONSerialization.jsonObject(
    with: Data(contentsOf: URL(fileURLWithPath: args[1]))) as! [[String: Any]]
let outURL = URL(fileURLWithPath: args[2])
try? FileManager.default.removeItem(at: outURL)

func rgb(_ hex: Int) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: 1)
}
let bg = rgb(0x0E1116), term = rgb(0x1A1E26), bar = rgb(0x242A33)
let white = rgb(0xF0F3F6), grey = rgb(0xA8B1BC), dim = rgb(0x6E7681)
let green = rgb(0x7EE787), amber = rgb(0xF2CC60), cyan = rgb(0x79C0FF)
let mono = CTFontCreateWithName("Menlo-Regular" as CFString, 17, nil)
let monoBold = CTFontCreateWithName("Menlo-Bold" as CFString, 17, nil)
func sans(_ size: CGFloat, bold: Bool = false) -> CTFont {
    CTFontCreateUIFontForLanguage(bold ? .emphasizedSystem : .system, size, nil)!
}

struct Line { var text: String; var color: CGColor; var font: CTFont }
struct Snap {
    var title: [String: Any]? = nil
    var caption = ""
    var lines: [Line] = []
    var cursor = false
    var seconds = 0.0
}

func colored(_ out: String) -> [Line] {
    let maxCols = 108
    var lines: [Line] = []
    for raw in out.components(separatedBy: "\n") {
        var color = grey, font = mono
        if raw.contains("Winddown active") || raw.hasPrefix("exit code: 2") { color = amber; font = monoBold }
        else if raw.hasPrefix("Closed ") || raw.hasPrefix("Pause cleared") { color = green; font = monoBold }
        else if raw.hasPrefix("# ") || raw.hasPrefix("**Where") { color = white; font = monoBold }
        else if raw.range(of: #"^\d\. "#, options: .regularExpression) != nil { color = cyan }
        var rest = Substring(raw)
        repeat {
            lines.append(Line(text: String(rest.prefix(maxCols)), color: color, font: font))
            rest = rest.dropFirst(maxCols)
        } while !rest.isEmpty
    }
    return lines
}

// Build the timeline: typing the command, then its real output, then a pause.
var snaps: [Snap] = []
for item in session {
    if item["kind"] as? String == "title" {
        snaps.append(Snap(title: item, seconds: item["hold"] as! Double))
        continue
    }
    var s = Snap(caption: item["caption"] as! String)
    s.seconds = 1.0
    s.cursor = true
    s.lines = [Line(text: "$ ", color: green, font: monoBold)]
    snaps.append(s)
    for (i, step) in (item["steps"] as! [[String: String]]).enumerated() {
        if i > 0 { s.lines.append(Line(text: "$ ", color: green, font: monoBold)) }
        let cmd = step["cmd"]!
        let idx = s.lines.count - 1
        var typed = ""
        for ch in cmd {
            typed.append(ch)
            s.lines[idx] = Line(text: "$ " + typed, color: white, font: monoBold)
            s.seconds = 0.035
            snaps.append(s)
        }
        s.seconds = 0.45
        snaps.append(s)
        s.cursor = false
        if !step["out"]!.isEmpty { s.lines += colored(step["out"]!) }
        s.lines.append(Line(text: "", color: grey, font: mono))
        s.seconds = 1.2
        snaps.append(s)
        s.cursor = true
    }
    s.cursor = false
    s.seconds = item["hold"] as! Double
    snaps.append(s)
}

func draw(_ ctx: CGContext, _ text: String, x: CGFloat, top: CGFloat, font: CTFont,
          color: CGColor, center: Bool = false) -> CGFloat {
    let attr = NSAttributedString(string: text, attributes: [
        kCTFontAttributeName as NSAttributedString.Key: font,
        kCTForegroundColorAttributeName as NSAttributedString.Key: color])
    let line = CTLineCreateWithAttributedString(attr)
    var ascent: CGFloat = 0, descent: CGFloat = 0, leading: CGFloat = 0
    let width = CGFloat(CTLineGetTypographicBounds(line, &ascent, &descent, &leading))
    ctx.textPosition = CGPoint(x: center ? (CGFloat(W) - width) / 2 : x,
                               y: CGFloat(H) - top - ascent)
    CTLineDraw(line, ctx)
    return x + width
}

func render(_ s: Snap, into ctx: CGContext) {
    ctx.setFillColor(bg)
    ctx.fill(CGRect(x: 0, y: 0, width: W, height: H))
    if let t = s.title {
        var y: CGFloat = 230
        _ = draw(ctx, t["title"] as! String, x: 0, top: y, font: sans(60, bold: true), color: white, center: true)
        y += 95
        _ = draw(ctx, t["subtitle"] as! String, x: 0, top: y, font: sans(30), color: green, center: true)
        y += 70
        for b in (t["body"] as! String).components(separatedBy: "\n") {
            _ = draw(ctx, b, x: 0, top: y, font: sans(22), color: grey, center: true)
            y += 36
        }
        return
    }
    var y: CGFloat = 34
    for (i, c) in s.caption.components(separatedBy: "\n").enumerated() {
        _ = draw(ctx, c, x: 60, top: y, font: sans(i == 0 ? 28 : 21, bold: i == 0),
                 color: i == 0 ? white : grey)
        y += i == 0 ? 42 : 32
    }
    let box = CGRect(x: 60, y: 40, width: CGFloat(W) - 120, height: CGFloat(H) - 40 - 150)
    ctx.setFillColor(term)
    ctx.addPath(CGPath(roundedRect: box, cornerWidth: 12, cornerHeight: 12, transform: nil))
    ctx.fillPath()
    ctx.setFillColor(bar)
    ctx.fill(CGRect(x: box.minX, y: box.maxY - 34, width: box.width, height: 22))
    ctx.addPath(CGPath(roundedRect: CGRect(x: box.minX, y: box.maxY - 34, width: box.width, height: 34),
                       cornerWidth: 12, cornerHeight: 12, transform: nil))
    ctx.fillPath()
    for (i, c) in [0xFF5F57, 0xFEBC2E, 0x28C840].enumerated() {
        ctx.setFillColor(rgb(c))
        ctx.fillEllipse(in: CGRect(x: box.minX + 16 + CGFloat(i) * 22, y: box.maxY - 23, width: 12, height: 12))
    }
    _ = draw(ctx, "~/code/api", x: 0, top: 158, font: sans(14), color: dim, center: true)
    let lineH: CGFloat = 25, maxLines = 19
    var top: CGFloat = 196
    let visible = s.lines.suffix(maxLines)
    for (i, l) in visible.enumerated() {
        let end = draw(ctx, l.text, x: 84, top: top, font: l.font, color: l.color)
        if s.cursor && i == visible.count - 1 {
            ctx.setFillColor(white)
            ctx.fill(CGRect(x: end + 2, y: CGFloat(H) - top - 21, width: 10, height: 20))
        }
        top += lineH
    }
}

let writer = try! AVAssetWriter(outputURL: outURL, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: W, AVVideoHeightKey: H])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
    kCVPixelBufferWidthKey as String: W, kCVPixelBufferHeightKey as String: H])
writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

var frame: Int64 = 0
var clock = 0.0
for s in snaps {
    var pb: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &pb)
    CVPixelBufferLockBaseAddress(pb!, [])
    let ctx = CGContext(data: CVPixelBufferGetBaseAddress(pb!), width: W, height: H, bitsPerComponent: 8,
                        bytesPerRow: CVPixelBufferGetBytesPerRow(pb!), space: CGColorSpaceCreateDeviceRGB(),
                        bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)!
    render(s, into: ctx)
    CVPixelBufferUnlockBaseAddress(pb!, [])
    clock += s.seconds
    while Double(frame) / Double(FPS) < clock {
        while !input.isReadyForMoreMediaData { usleep(1000) }
        adaptor.append(pb!, withPresentationTime: CMTime(value: frame, timescale: FPS))
        frame += 1
    }
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
print(writer.status == .completed ? "wrote \(outURL.path) (\(frame) frames, \(String(format: "%.1f", clock))s)"
                                  : "failed: \(String(describing: writer.error))")
