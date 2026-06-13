'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { ArrowLeft, Plus, Loader2, RefreshCw } from 'lucide-react'
import { charactersApi, relationshipsApi } from '@/lib/api'
import { Character, CharacterGraph, CharacterRelationship, RelationshipType } from '@/lib/types'
import { toast } from 'sonner'

// ── Constants ─────────────────────────────────────────────────────────────────

const REL_COLOR: Record<RelationshipType, string> = {
  ally:     '#34d399',  // green
  rival:    '#fbbf24',  // amber
  family:   '#a78bfa',  // violet
  romantic: '#f472b6',  // pink
  mentor:   '#38bdf8',  // sky
  enemy:    '#f87171',  // red
  neutral:  '#5c6391',  // grey
}

const NODE_RADIUS = 28
const LABEL_OFFSET = 44

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodePos {
  characterId: string
  x: number
  y: number
}

interface Props {
  storyId:   string
  onBack:    () => void
  onSelect:  (char: Character) => void   // navigate to profile panel
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function initCircleLayout(nodes: Character[], cx: number, cy: number, r: number): NodePos[] {
  if (nodes.length === 0) return []
  if (nodes.length === 1) return [{ characterId: nodes[0].character_id, x: cx, y: cy }]
  return nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2
    return { characterId: n.character_id, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
  })
}

function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CharacterRelationshipGraph({ storyId, onBack, onSelect }: Props) {
  const [graph,    setGraph]    = useState<CharacterGraph | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(false)
  const [positions, setPositions] = useState<NodePos[]>([])

  const svgRef  = useRef<SVGSVGElement>(null)
  const [svgSize, setSvgSize] = useState({ w: 288, h: 400 })

  // Drag state
  const dragging    = useRef<string | null>(null)
  const dragOffset  = useRef({ dx: 0, dy: 0 })

  // Selected edge / node for tooltip
  const [selectedEdge, setSelectedEdge] = useState<CharacterRelationship | null>(null)
  const [hoverNode, setHoverNode]        = useState<string | null>(null)

  // ── Load graph ─────────────────────────────────────────────────────────────

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(false)
    setSelectedEdge(null)
    try {
      const res = await charactersApi.graph(storyId)
      // Defensive: tolerate a missing/!==array nodes/edges shape from the API.
      const data: CharacterGraph = {
        nodes: Array.isArray(res.data?.nodes) ? res.data.nodes : [],
        edges: Array.isArray(res.data?.edges) ? res.data.edges : [],
      }
      setGraph(data)
    } catch {
      setError(true)
      toast.error('Failed to load character graph')
    } finally {
      setLoading(false)
    }
  }, [storyId])

  useEffect(() => { loadGraph() }, [loadGraph])

  // ── Layout ───────────────────────────────────────────────────────────────
  // Positions are computed here (NOT inside loadGraph) so they are recomputed
  // once the SVG is actually mounted and measured. The previous code set
  // positions only when svgRef.current existed during the fetch — but the SVG
  // is unmounted while `loading` is true, so positions stayed empty and every
  // node/edge rendered null (the "empty graph" bug). Existing positions are
  // preserved so dragged nodes don't jump when the graph refreshes.
  useEffect(() => {
    if (!graph) return
    const { w, h } = svgSize
    const r = Math.max(Math.min(w, h) / 2 - LABEL_OFFSET - NODE_RADIUS - 16, 60)
    const layout = initCircleLayout(graph.nodes, w / 2, h / 2, r)
    setPositions(prev => {
      const byId = new Map(prev.map(p => [p.characterId, p]))
      return layout.map(l => byId.get(l.characterId) ?? l)
    })
  }, [graph, svgSize])

  // ── Resize observer ────────────────────────────────────────────────────────
  // Re-attach whenever the SVG (un)mounts — it is only rendered once loading is
  // false, so an empty-dep effect would attach to a null ref and never measure.

  useEffect(() => {
    if (!svgRef.current) return
    // Seed from the real measured size immediately on mount.
    const rect = svgRef.current.getBoundingClientRect()
    if (rect.width && rect.height) setSvgSize({ w: rect.width, h: rect.height })
    const obs = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width && height) setSvgSize({ w: width, h: height })
      }
    })
    obs.observe(svgRef.current)
    return () => obs.disconnect()
  }, [loading, error])

  // ── Drag handlers ──────────────────────────────────────────────────────────

  const getNodePos = (id: string): NodePos | undefined =>
    positions.find(p => p.characterId === id)

  const onMouseDown = useCallback((e: React.MouseEvent, characterId: string) => {
    e.stopPropagation()
    e.preventDefault()
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const pos  = getNodePos(characterId)
    if (!pos) return
    dragging.current  = characterId
    dragOffset.current = {
      dx: e.clientX - rect.left - pos.x,
      dy: e.clientY - rect.top  - pos.y,
    }
  }, [positions])

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const x = e.clientX - rect.left  - dragOffset.current.dx
    const y = e.clientY - rect.top   - dragOffset.current.dy
    setPositions(prev => prev.map(p =>
      p.characterId === dragging.current ? { ...p, x, y } : p
    ))
  }, [])

  const onMouseUp = useCallback(() => {
    dragging.current = null
  }, [])

  // ── Delete relationship ────────────────────────────────────────────────────

  const deleteEdge = async (rel: CharacterRelationship) => {
    try {
      await relationshipsApi.delete(storyId, rel.from_character_id, rel.relationship_id)
      setGraph(prev => prev
        ? { ...prev, edges: prev.edges.filter(e => e.relationship_id !== rel.relationship_id) }
        : prev
      )
      setSelectedEdge(null)
      toast.success('Relationship removed')
    } catch {
      toast.error('Failed to remove relationship')
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const chars = graph?.nodes ?? []
  const edges = graph?.edges ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f2440] flex items-center gap-2 flex-shrink-0">
        <button onClick={onBack} className="text-[#5c6391] hover:text-[#9da3c8] transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <span className="text-xs font-medium text-[#9da3c8] flex-1">Relationship Graph</span>
        <button
          onClick={loadGraph}
          disabled={loading}
          className="text-[#3d4466] hover:text-[#9da3c8] transition-colors disabled:opacity-40"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* SVG canvas */}
      <div className="flex-1 relative overflow-hidden">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="w-5 h-5 text-[#3d4466] animate-spin" />
          </div>
        ) : error ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4">
            <p className="text-xs text-red-300 text-center">Couldn’t load the relationship graph.</p>
            <button
              onClick={loadGraph}
              className="text-[11px] px-3 py-1 rounded border border-[#2e3454] text-[#9da3c8] hover:text-white hover:border-[#3d4466]"
            >
              Retry
            </button>
          </div>
        ) : chars.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-xs text-[#3d4466] text-center px-4">
              No characters yet. Create characters and add relationships to see the graph.
            </p>
          </div>
        ) : (
          <svg
            ref={svgRef}
            className="w-full h-full select-none"
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
            onClick={() => setSelectedEdge(null)}
          >
            {/* Edges */}
            {edges.map(edge => {
              const fromPos = getNodePos(edge.from_character_id)
              const toPos   = getNodePos(edge.to_character_id)
              if (!fromPos || !toPos) return null

              const dx   = toPos.x - fromPos.x
              const dy   = toPos.y - fromPos.y
              const len  = Math.sqrt(dx * dx + dy * dy) || 1
              const ux   = dx / len
              const uy   = dy / len

              // Offset so lines don't overlap node circles
              const x1 = fromPos.x + ux * NODE_RADIUS
              const y1 = fromPos.y + uy * NODE_RADIUS
              const x2 = toPos.x   - ux * (NODE_RADIUS + 6)  // extra for arrowhead
              const y2 = toPos.y   - uy * (NODE_RADIUS + 6)

              const midX = (x1 + x2) / 2
              const midY = (y1 + y2) / 2

              const color   = REL_COLOR[edge.relationship_type] ?? '#5c6391'
              const isSelected = selectedEdge?.relationship_id === edge.relationship_id
              const markerId = `arrow-${edge.relationship_id}`

              return (
                <g key={edge.relationship_id}>
                  <defs>
                    <marker
                      id={markerId}
                      markerWidth="6"
                      markerHeight="6"
                      refX="3"
                      refY="3"
                      orient="auto"
                    >
                      <path d="M0,0 L6,3 L0,6 Z" fill={color} opacity={isSelected ? 1 : 0.6} />
                    </marker>
                  </defs>

                  {/* Invisible hit area */}
                  <line
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    strokeWidth={12}
                    stroke="transparent"
                    style={{ cursor: 'pointer' }}
                    onClick={e => { e.stopPropagation(); setSelectedEdge(edge) }}
                  />

                  {/* Visible line */}
                  <line
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={color}
                    strokeWidth={isSelected ? 2 : 1.5}
                    opacity={isSelected ? 1 : 0.5}
                    markerEnd={`url(#${markerId})`}
                    style={{ cursor: 'pointer' }}
                    onClick={e => { e.stopPropagation(); setSelectedEdge(edge) }}
                  />

                  {/* Mutual indicator */}
                  {edge.is_mutual && (
                    <line
                      x1={toPos.x - ux * NODE_RADIUS}
                      y1={toPos.y - uy * NODE_RADIUS}
                      x2={fromPos.x + ux * (NODE_RADIUS + 6)}
                      y2={fromPos.y + uy * (NODE_RADIUS + 6)}
                      stroke={color}
                      strokeWidth={1.5}
                      opacity={isSelected ? 1 : 0.3}
                      strokeDasharray="3 2"
                    />
                  )}

                  {/* Edge label */}
                  <text
                    x={midX}
                    y={midY - 4}
                    textAnchor="middle"
                    fontSize={9}
                    fill={color}
                    opacity={0.7}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {edge.relationship_type}
                  </text>
                </g>
              )
            })}

            {/* Nodes */}
            {chars.map(char => {
              const pos = getNodePos(char.character_id)
              if (!pos) return null
              const isHovered = hoverNode === char.character_id

              return (
                <g
                  key={char.character_id}
                  transform={`translate(${pos.x},${pos.y})`}
                  style={{ cursor: 'grab' }}
                  onMouseDown={e => onMouseDown(e, char.character_id)}
                  onMouseEnter={() => setHoverNode(char.character_id)}
                  onMouseLeave={() => setHoverNode(null)}
                  onDoubleClick={() => onSelect(char)}
                >
                  {/* Outer ring on hover */}
                  {isHovered && (
                    <circle r={NODE_RADIUS + 4} fill="none" stroke="#f59e0b" strokeWidth={1} opacity={0.4} />
                  )}

                  {/* Node circle */}
                  <circle
                    r={NODE_RADIUS}
                    fill="#1f2440"
                    stroke={isHovered ? '#f59e0b' : '#2e3454'}
                    strokeWidth={1.5}
                  />

                  {/* Initials */}
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={11}
                    fontWeight={600}
                    fill={isHovered ? '#f59e0b' : '#9da3c8'}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {initials(char.name)}
                  </text>

                  {/* Status dot */}
                  <circle
                    r={4}
                    cx={NODE_RADIUS - 5}
                    cy={-(NODE_RADIUS - 5)}
                    fill={char.status === 'active' ? '#34d399' : char.status === 'deceased' ? '#f87171' : '#5c6391'}
                  />

                  {/* Name label */}
                  <text
                    y={LABEL_OFFSET - 8}
                    textAnchor="middle"
                    fontSize={10}
                    fill="#e8eaf6"
                    fontWeight={500}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {char.name.length > 14 ? char.name.slice(0, 13) + '…' : char.name}
                  </text>
                </g>
              )
            })}
          </svg>
        )}

        {/* Characters exist but no edges — show nodes + a non-blocking hint. */}
        {!loading && !error && chars.length > 0 && edges.length === 0 && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 pointer-events-none">
            <span className="text-[10px] text-[#5c6391] bg-[#0d0f1a]/85 border border-[#1f2440] px-2 py-1 rounded">
              No relationships detected yet.
            </span>
          </div>
        )}
      </div>

      {/* Edge detail panel */}
      {selectedEdge && (() => {
        const fromChar = chars.find(c => c.character_id === selectedEdge.from_character_id)
        const toChar   = chars.find(c => c.character_id === selectedEdge.to_character_id)
        const color    = REL_COLOR[selectedEdge.relationship_type] ?? '#5c6391'
        return (
          <div className="flex-shrink-0 border-t border-[#1f2440] p-3 bg-[#0d0f1a]">
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-[#9da3c8] mb-0.5">
                  <span className="font-medium" style={{ color }}>{selectedEdge.relationship_type}</span>
                  {' '}·{' '}
                  <span className="text-[#5c6391] capitalize">{selectedEdge.strength}</span>
                  {selectedEdge.is_mutual && <span className="text-[#3d4466] ml-1">(mutual)</span>}
                </p>
                <p className="text-[11px] text-[#5c6391]">
                  {fromChar?.name ?? '?'} → {toChar?.name ?? '?'}
                </p>
                {selectedEdge.description && (
                  <p className="text-[11px] text-[#3d4466] mt-1 line-clamp-2">{selectedEdge.description}</p>
                )}
              </div>
              <button
                onClick={() => deleteEdge(selectedEdge)}
                className="text-[#3d4466] hover:text-red-400 transition-colors flex-shrink-0 text-[11px]"
              >
                Remove
              </button>
            </div>
          </div>
        )
      })()}

      {/* Legend */}
      {!loading && chars.length > 0 && (
        <div className="flex-shrink-0 border-t border-[#1f2440] p-2 flex flex-wrap gap-x-2 gap-y-1">
          {Object.entries(REL_COLOR).map(([type, color]) => (
            <span key={type} className="flex items-center gap-1 text-[9px]" style={{ color }}>
              <span className="w-2 h-0.5 rounded" style={{ background: color }} />
              {type}
            </span>
          ))}
          <span className="text-[9px] text-[#3d4466] ml-auto">Double-click node → profile</span>
        </div>
      )}
    </div>
  )
}
