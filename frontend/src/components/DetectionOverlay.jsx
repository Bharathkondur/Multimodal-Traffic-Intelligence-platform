import React, { useEffect, useRef } from 'react'

const VEHICLE_COLORS = {
  car: '#3b82f6',
  truck: '#ef4444',
  bus: '#f59e0b',
  motorcycle: '#8b5cf6',
  bicycle: '#10b981',
  pedestrian: '#ec4899'
}

const DetectionOverlay = ({ detections = [], width = 1280, height = 720 }) => {
  const svgRef = useRef(null)

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    // Clear previous elements
    while (svg.firstChild) {
      svg.removeChild(svg.firstChild)
    }

    // Scale factors
    const scaleX = width / 1280
    const scaleY = height / 720

    detections.forEach((detection) => {
      const { bbox, type, confidence, track_id, is_incident, trajectory = [], plate_number } = detection

      if (!bbox || !bbox.length) return

      const [x1, y1, x2, y2] = bbox
      const x = x1 * scaleX
      const y = y1 * scaleY
      const w = (x2 - x1) * scaleX
      const h = (y2 - y1) * scaleY

      const color = VEHICLE_COLORS[type?.toLowerCase()] || VEHICLE_COLORS.car
      const lineWidth = is_incident ? 3 : 2

      // Draw trajectory/trail if available
      if (trajectory && trajectory.length > 1) {
        const trailGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
        trailGroup.setAttribute('opacity', '0.5')

        for (let i = 0; i < trajectory.length - 1; i++) {
          const [x1_traj, y1_traj] = trajectory[i]
          const [x2_traj, y2_traj] = trajectory[i + 1]

          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
          line.setAttribute('x1', x1_traj * scaleX)
          line.setAttribute('y1', y1_traj * scaleY)
          line.setAttribute('x2', x2_traj * scaleX)
          line.setAttribute('y2', y2_traj * scaleY)
          line.setAttribute('stroke', color)
          line.setAttribute('stroke-width', '1')
          line.setAttribute('stroke-dasharray', '5,5')
          line.setAttribute('opacity', String(0.3 + (i / trajectory.length) * 0.7))

          trailGroup.appendChild(line)
        }

        svg.appendChild(trailGroup)
      }

      // Draw bounding box
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      rect.setAttribute('x', x)
      rect.setAttribute('y', y)
      rect.setAttribute('width', w)
      rect.setAttribute('height', h)
      rect.setAttribute('fill', 'none')
      rect.setAttribute('stroke', color)
      rect.setAttribute('stroke-width', lineWidth)

      if (is_incident) {
        // Pulsing effect for incidents
        rect.style.animation = 'pulse 1s infinite'
        rect.style.filter = 'drop-shadow(0 0 8px ' + color + ')'
      }

      svg.appendChild(rect)

      // Draw detection label (type + confidence)
      const labelText = `${type || 'vehicle'}: ${(confidence * 100).toFixed(0)}%${track_id ? ` (${track_id})` : ''}`
      const textElement = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      textElement.setAttribute('x', x + 5)
      textElement.setAttribute('y', y - 8)
      textElement.setAttribute('font-size', '12')
      textElement.setAttribute('font-weight', 'bold')
      textElement.setAttribute('fill', color)
      textElement.setAttribute('font-family', 'monospace')
      textElement.textContent = labelText

      const textBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      const textWidth = labelText.length * 6
      textBg.setAttribute('x', x)
      textBg.setAttribute('y', y - 22)
      textBg.setAttribute('width', textWidth + 10)
      textBg.setAttribute('height', 18)
      textBg.setAttribute('fill', 'rgba(0, 0, 0, 0.7)')
      textBg.setAttribute('stroke', color)
      textBg.setAttribute('stroke-width', '1')

      svg.appendChild(textBg)
      svg.appendChild(textElement)

      // Draw license plate label below the bounding box if OCR found one
      if (plate_number) {
        const plateText = `🔤 ${plate_number}`
        const plateEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
        plateEl.setAttribute('x', x + 5)
        plateEl.setAttribute('y', y + h + 14)
        plateEl.setAttribute('font-size', '12')
        plateEl.setAttribute('font-weight', 'bold')
        plateEl.setAttribute('fill', '#facc15')
        plateEl.setAttribute('font-family', 'monospace')
        plateEl.textContent = plateText

        const plateBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
        plateBg.setAttribute('x', x)
        plateBg.setAttribute('y', y + h + 2)
        plateBg.setAttribute('width', plateText.length * 7 + 10)
        plateBg.setAttribute('height', 18)
        plateBg.setAttribute('fill', 'rgba(0,0,0,0.8)')
        plateBg.setAttribute('stroke', '#facc15')
        plateBg.setAttribute('stroke-width', '1')

        svg.appendChild(plateBg)
        svg.appendChild(plateEl)
      }

      // Draw corner markers
      const cornerSize = 8
      const cornerColor = is_incident ? '#ef4444' : color

      const corners = [
        { x: x, y: y }, // top-left
        { x: x + w, y: y }, // top-right
        { x: x, y: y + h }, // bottom-left
        { x: x + w, y: y + h } // bottom-right
      ]

      corners.forEach(({ x: cx, y: cy }) => {
        const cornerGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')

        const hLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
        hLine.setAttribute('x1', cx - cornerSize)
        hLine.setAttribute('y1', cy)
        hLine.setAttribute('x2', cx + cornerSize)
        hLine.setAttribute('y2', cy)
        hLine.setAttribute('stroke', cornerColor)
        hLine.setAttribute('stroke-width', '2')
        cornerGroup.appendChild(hLine)

        const vLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
        vLine.setAttribute('x1', cx)
        vLine.setAttribute('y1', cy - cornerSize)
        vLine.setAttribute('x2', cx)
        vLine.setAttribute('y2', cy + cornerSize)
        vLine.setAttribute('stroke', cornerColor)
        vLine.setAttribute('stroke-width', '2')
        cornerGroup.appendChild(vLine)

        svg.appendChild(cornerGroup)
      })
    })

    // Add legend
    const legendY = 20
    let legendX = width - 200

    Object.entries(VEHICLE_COLORS).forEach(([type, color], index) => {
      const legendGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')

      const colorBox = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
      colorBox.setAttribute('x', legendX)
      colorBox.setAttribute('y', legendY + index * 20)
      colorBox.setAttribute('width', '12')
      colorBox.setAttribute('height', '12')
      colorBox.setAttribute('fill', color)
      legendGroup.appendChild(colorBox)

      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text')
      label.setAttribute('x', legendX + 16)
      label.setAttribute('y', legendY + index * 20 + 10)
      label.setAttribute('font-size', '11')
      label.setAttribute('fill', '#94a3b8')
      label.setAttribute('font-family', 'monospace')
      label.textContent = type.charAt(0).toUpperCase() + type.slice(1)
      legendGroup.appendChild(label)

      svg.appendChild(legendGroup)
    })
  }, [detections, width, height])

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
