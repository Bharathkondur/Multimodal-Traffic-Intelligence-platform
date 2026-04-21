import React, { useEffect, useRef, useMemo } from 'react'

/**
 * Scene Intelligence overlay.
 *
 * Renders bounding boxes, corner markers, trajectories, track IDs and
 * plate numbers for the full 80-class COCO taxonomy (YOLO26/11/v8).
 *
 * Color strategy:
 *   - Well-known "hero" classes get curated brand-friendly colors.
 *   - Everything else gets a deterministic hash-based HSL color so
 *     two boxes of the same class always render the same hue across
 *     frames (important for tracking readability).
 *   - Legend only shows categories actually present in the current
 *     frame — keeps the HUD from exploding to 80 swatches.
 */

// Curated palette for the classes most likely to show up — ensures the
// common UX (person blue, car green, truck amber, etc.) stays consistent
// across demos. Keys are lower-cased COCO class names.
const CURATED_COLORS = {
  // people & core vehicles
  person: '#38bdf8',
  bicycle: '#10b981',
  car: '#3b82f6',
  motorcycle: '#8b5cf6',
  bus: '#f59e0b',
  truck: '#ef4444',
  train: '#f97316',
  airplane: '#06b6d4',
  boat: '#0ea5e9',
  pedestrian: '#38bdf8', // alias
  van: '#6366f1',
  // infrastructure
  'traffic light': '#eab308',
  'stop sign': '#dc2626',
  'fire hydrant': '#f87171',
  'parking meter': '#a78bfa',
  bench: '#64748b',
  // belongings (useful for unattended-bag rules)
  backpack: '#ec4899',
  umbrella: '#d946ef',
  handbag: '#f472b6',
  suitcase: '#e879f9',
  tie: '#c084fc',
  // animals
  dog: '#fb923c',
  cat: '#fbbf24',
  bird: '#fde047',
  horse: '#d97706',
  cow: '#b45309',
  sheep: '#fcd34d',
  // common indoor
  chair: '#94a3b8',
  couch: '#64748b',
  laptop: '#22d3ee',
  'cell phone': '#67e8f9',
  bottle: '#34d399',
  cup: '#4ade80',
}

// Super-category groupings for the legend.
const CATEGORY = {
  person: 'person',
  // vehicles
  bicycle: 'vehicle', car: 'vehicle', motorcycle: 'vehicle',
  airplane: 'vehicle', bus: 'vehicle', train: 'vehicle',
  truck: 'vehicle', boat: 'vehicle', van: 'vehicle',
  // animals
  bird: 'animal', cat: 'animal', dog: 'animal', horse: 'animal',
  sheep: 'animal', cow: 'animal', elephant: 'animal', bear: 'animal',
  zebra: 'animal', giraffe: 'animal',
  // infrastructure
  'traffic light': 'infra', 'fire hydrant': 'infra', 'stop sign': 'infra',
  'parking meter': 'infra', bench: 'infra',
  // belongings
  backpack: 'belongings', umbrella: 'belongings', handbag: 'belongings',
  tie: 'belongings', suitcase: 'belongings',
}

const CATEGORY_ORDER = ['person', 'vehicle', 'animal', 'belongings', 'infra', 'object']

// Deterministic hash → hue for unknown classes.
function hashHue(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h) + str.charCodeAt(i)
    h |= 0
  }
  // Skew away from reds (reserve red spectrum for alerts) by adding 60°.
  return ((Math.abs(h) % 300) + 60) % 360
}

function colorFor(rawType) {
  const type = (rawType || '').toLowerCase().trim()
  if (!type) return '#38bdf8'
  if (CURATED_COLORS[type]) return CURATED_COLORS[type]
  const hue = hashHue(type)
  return `hsl(${hue}, 70%, 60%)`
}

function categoryFor(rawType) {
  const type = (rawType || '').toLowerCase().trim()
  return CATEGORY[type] || 'object'
}

const CATEGORY_LABEL = {
  person: 'People',
  vehicle: 'Vehicles',
  animal: 'Animals',
  belongings: 'Belongings',
  infra: 'Infrastructure',
  object: 'Other',
}

const CATEGORY_COLOR = {
  person: '#38bdf8',
  vehicle: '#3b82f6',
  animal: '#fb923c',
  belongings: '#ec4899',
  infra: '#eab308',
  object: '#94a3b8',
}

const DetectionOverlay = ({
  detections = [],
  width = 1280,
  height = 720,
  poseKeypoints = [],
  zones = [],
}) => {
  const svgRef = useRef(null)

  // Build the legend entries from what's actually present in the frame.
  const legendEntries = useMemo(() => {
    const counts = {}
    detections.forEach((d) => {
      const type = (d.type || d.class_name || 'object').toLowerCase()
      const cat = categoryFor(type)
      counts[cat] = (counts[cat] || 0) + 1
    })
    return CATEGORY_ORDER
      .filter((c) => counts[c])
      .map((c) => ({ category: c, count: counts[c] }))
  }, [detections])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    // Clear previous elements (but keep the <style> node at [0])
    while (svg.childNodes.length > 1) {
      svg.removeChild(svg.lastChild)
    }

    // Scale factors (detections are emitted at 1280×720 stream resolution)
    const scaleX = width / 1280
    const scaleY = height / 720
    const NS = 'http://www.w3.org/2000/svg'

    // --- Zones (drawn first so boxes sit on top) -----------------------
    zones.forEach((zone) => {
      if (!zone.points || zone.points.length < 3) return
      const polygon = document.createElementNS(NS, 'polygon')
      const pts = zone.points
        .map(([px, py]) => `${px * scaleX},${py * scaleY}`)
        .join(' ')
      polygon.setAttribute('points', pts)
      polygon.setAttribute('fill', zone.color || '#00d4ff')
      polygon.setAttribute('fill-opacity', '0.08')
      polygon.setAttribute('stroke', zone.color || '#00d4ff')
      polygon.setAttribute('stroke-width', '2')
      polygon.setAttribute('stroke-dasharray', '8,4')
      svg.appendChild(polygon)

      if (zone.name) {
        const [fx, fy] = zone.points[0]
        const label = document.createElementNS(NS, 'text')
        label.setAttribute('x', fx * scaleX + 8)
        label.setAttribute('y', fy * scaleY + 18)
        label.setAttribute('font-size', '13')
        label.setAttribute('font-weight', '700')
        label.setAttribute('font-family', 'monospace')
        label.setAttribute('fill', zone.color || '#00d4ff')
        label.textContent = zone.name.toUpperCase()
        svg.appendChild(label)
      }
    })

    // --- Detections -----------------------------------------------------
    detections.forEach((detection) => {
      const {
        bbox,
        type,
        class_name,
        confidence,
        track_id,
        is_incident,
        trajectory = [],
        plate_number,
        action,
      } = detection

      if (!bbox || !bbox.length) return

      const [x1, y1, x2, y2] = bbox
      const x = x1 * scaleX
      const y = y1 * scaleY
      const w = (x2 - x1) * scaleX
      const h = (y2 - y1) * scaleY

      const displayType = (type || class_name || 'object').toLowerCase()
      const color = colorFor(displayType)
      const lineWidth = is_incident ? 3 : 2

      // Trajectory trail
      if (trajectory && trajectory.length > 1) {
        const trailGroup = document.createElementNS(NS, 'g')
        trailGroup.setAttribute('opacity', '0.5')
        for (let i = 0; i < trajectory.length - 1; i++) {
          const [x1_t, y1_t] = trajectory[i]
          const [x2_t, y2_t] = trajectory[i + 1]
          const line = document.createElementNS(NS, 'line')
          line.setAttribute('x1', x1_t * scaleX)
          line.setAttribute('y1', y1_t * scaleY)
          line.setAttribute('x2', x2_t * scaleX)
          line.setAttribute('y2', y2_t * scaleY)
          line.setAttribute('stroke', color)
          line.setAttribute('stroke-width', '1')
          line.setAttribute('stroke-dasharray', '5,5')
          line.setAttribute('opacity', String(0.3 + (i / trajectory.length) * 0.7))
          trailGroup.appendChild(line)
        }
        svg.appendChild(trailGroup)
      }

      // Bounding box
      const rect = document.createElementNS(NS, 'rect')
      rect.setAttribute('x', x)
      rect.setAttribute('y', y)
      rect.setAttribute('width', w)
      rect.setAttribute('height', h)
      rect.setAttribute('fill', 'none')
      rect.setAttribute('stroke', color)
      rect.setAttribute('stroke-width', lineWidth)

      if (is_incident) {
        rect.style.animation = 'pulse 1s infinite'
        rect.style.filter = `drop-shadow(0 0 8px ${color})`
      }
      svg.appendChild(rect)

      // Label: class · conf% · (track_id) · action
      const confPct = confidence != null
        ? ` ${(confidence * 100).toFixed(0)}%`
        : ''
      const trackStr = track_id ? ` #${track_id}` : ''
      const actionStr = action && action !== 'unknown' ? ` · ${action}` : ''
      const labelText = `${displayType}${confPct}${trackStr}${actionStr}`

      const charW = 6.2
      const textWidth = Math.min(labelText.length * charW + 10, Math.max(w, 90))

      const textBg = document.createElementNS(NS, 'rect')
      textBg.setAttribute('x', x)
      textBg.setAttribute('y', y - 22)
      textBg.setAttribute('width', textWidth)
      textBg.setAttribute('height', 18)
      textBg.setAttribute('fill', 'rgba(8, 12, 16, 0.85)')
      textBg.setAttribute('stroke', color)
      textBg.setAttribute('stroke-width', '1')
      svg.appendChild(textBg)

      const textElement = document.createElementNS(NS, 'text')
      textElement.setAttribute('x', x + 5)
      textElement.setAttribute('y', y - 8)
      textElement.setAttribute('font-size', '12')
      textElement.setAttribute('font-weight', 'bold')
      textElement.setAttribute('fill', color)
      textElement.setAttribute('font-family', 'monospace')
      textElement.textContent = labelText
      svg.appendChild(textElement)

      // Plate OCR label below box
      if (plate_number) {
        const plateText = `PLATE ${plate_number}`
        const plateBg = document.createElementNS(NS, 'rect')
        plateBg.setAttribute('x', x)
        plateBg.setAttribute('y', y + h + 2)
        plateBg.setAttribute('width', plateText.length * charW + 10)
        plateBg.setAttribute('height', 18)
        plateBg.setAttribute('fill', 'rgba(8, 12, 16, 0.9)')
        plateBg.setAttribute('stroke', '#facc15')
        plateBg.setAttribute('stroke-width', '1')
        svg.appendChild(plateBg)

        const plateEl = document.createElementNS(NS, 'text')
        plateEl.setAttribute('x', x + 5)
        plateEl.setAttribute('y', y + h + 14)
        plateEl.setAttribute('font-size', '12')
        plateEl.setAttribute('font-weight', 'bold')
        plateEl.setAttribute('fill', '#facc15')
        plateEl.setAttribute('font-family', 'monospace')
        plateEl.textContent = plateText
        svg.appendChild(plateEl)
      }

      // Corner markers
      const cornerSize = 8
      const cornerColor = is_incident ? '#ef4444' : color
      const corners = [
        { x, y },
        { x: x + w, y },
        { x, y: y + h },
        { x: x + w, y: y + h },
      ]
      corners.forEach(({ x: cx, y: cy }) => {
        const h1 = document.createElementNS(NS, 'line')
        h1.setAttribute('x1', cx - cornerSize)
        h1.setAttribute('y1', cy)
        h1.setAttribute('x2', cx + cornerSize)
        h1.setAttribute('y2', cy)
        h1.setAttribute('stroke', cornerColor)
        h1.setAttribute('stroke-width', '2')
        svg.appendChild(h1)

        const v1 = document.createElementNS(NS, 'line')
        v1.setAttribute('x1', cx)
        v1.setAttribute('y1', cy - cornerSize)
        v1.setAttribute('x2', cx)
        v1.setAttribute('y2', cy + cornerSize)
        v1.setAttribute('stroke', cornerColor)
        v1.setAttribute('stroke-width', '2')
        svg.appendChild(v1)
      })
    })

    // --- Pose keypoints (minimal skeleton overlay) ---------------------
    // COCO-17 skeleton edges (keypoint indices)
    const SKELETON = [
      [5, 7], [7, 9], [6, 8], [8, 10],           // arms
      [5, 6], [5, 11], [6, 12], [11, 12],        // torso
      [11, 13], [13, 15], [12, 14], [14, 16],    // legs
      [0, 1], [0, 2], [1, 3], [2, 4],            // head
    ]
    poseKeypoints.forEach((person) => {
      const kps = person.keypoints || []
      SKELETON.forEach(([a, b]) => {
        const pa = kps[a]
        const pb = kps[b]
        if (!pa || !pb) return
        if ((pa[2] ?? 1) < 0.3 || (pb[2] ?? 1) < 0.3) return
        const line = document.createElementNS(NS, 'line')
        line.setAttribute('x1', pa[0] * scaleX)
        line.setAttribute('y1', pa[1] * scaleY)
        line.setAttribute('x2', pb[0] * scaleX)
        line.setAttribute('y2', pb[1] * scaleY)
        line.setAttribute('stroke', '#00d4ff')
        line.setAttribute('stroke-width', '2')
        line.setAttribute('stroke-linecap', 'round')
        line.setAttribute('opacity', '0.85')
        svg.appendChild(line)
      })
      kps.forEach((kp) => {
        if (!kp || (kp[2] ?? 1) < 0.3) return
        const dot = document.createElementNS(NS, 'circle')
        dot.setAttribute('cx', kp[0] * scaleX)
        dot.setAttribute('cy', kp[1] * scaleY)
        dot.setAttribute('r', '2.5')
        dot.setAttribute('fill', '#00d4ff')
        svg.appendChild(dot)
      })
    })

    // --- Legend (category-rolled-up) -----------------------------------
    const legendY = 20
    const legendX = width - 190
    legendEntries.forEach((entry, index) => {
      const box = document.createElementNS(NS, 'rect')
      box.setAttribute('x', legendX)
      box.setAttribute('y', legendY + index * 22)
      box.setAttribute('width', '14')
      box.setAttribute('height', '14')
      box.setAttribute('fill', CATEGORY_COLOR[entry.category])
      box.setAttribute('rx', '2')
      svg.appendChild(box)

      const label = document.createElementNS(NS, 'text')
      label.setAttribute('x', legendX + 20)
      label.setAttribute('y', legendY + index * 22 + 12)
      label.setAttribute('font-size', '12')
      label.setAttribute('fill', '#cbd5e1')
      label.setAttribute('font-family', 'monospace')
      label.textContent = `${CATEGORY_LABEL[entry.category]} · ${entry.count}`
      svg.appendChild(label)
    })
  }, [detections, poseKeypoints, zones, width, height, legendEntries])

  return (
    <svg
      ref={svgRef}
      className="absolute inset-0 pointer-events-none"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </svg>
  )
}

export default DetectionOverlay
