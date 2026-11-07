// Reads image paths (one per line) from stdin, prints JSON {path: [[x,y,w,h],...]} as fractions, top-left origin,
// in the EXIF-oriented image. Used by detect_faces.py.
import Foundation
import Vision
import ImageIO

var out: [String: [[Double]]] = [:]
var failed: [String] = []
while let line = readLine() {
    let path = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if path.isEmpty { continue }
    let url = URL(fileURLWithPath: path) as CFURL
    guard let src = CGImageSourceCreateWithURL(url, nil),
          let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else { failed.append(path); continue }
    var orient = CGImagePropertyOrientation.up
    if let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
       let o = props[kCGImagePropertyOrientation] as? UInt32,
       let po = CGImagePropertyOrientation(rawValue: o) { orient = po }
    let req = VNDetectFaceRectanglesRequest()
    let handler = VNImageRequestHandler(cgImage: cg, orientation: orient, options: [:])
    do {
        try handler.perform([req])
        var boxes: [[Double]] = []
        for r in (req.results ?? []) {
            let b = r.boundingBox  // normalised, bottom-left origin, in oriented image space
            boxes.append([Double(b.minX), Double(1.0 - b.maxY), Double(b.width), Double(b.height)])
        }
        out[path] = boxes
    } catch { failed.append(path) }
}
let data = try! JSONSerialization.data(withJSONObject: ["faces": out, "failed": failed], options: [])
FileHandle.standardOutput.write(data)
