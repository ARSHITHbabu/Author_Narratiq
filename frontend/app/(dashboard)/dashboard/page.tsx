'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Feather, Plus, BookOpen, MoreVertical, Trash2, Edit3,
  LogOut, User, BarChart3, Clock, ChevronRight, Loader2, Search
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { projectsApi } from '@/lib/api'
import { Story } from '@/lib/types'
import { toast } from 'sonner'
import { formatDistanceToNow } from 'date-fns'

function WordCountBadge({ count }: { count: number }) {
  const k = count >= 1000 ? `${(count / 1000).toFixed(1)}k` : count.toString()
  return <span className="text-xs text-[#5c6391]">{k} words</span>
}

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const router = useRouter()
  const [stories, setStories] = useState<Story[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [showNewModal, setShowNewModal] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [menuOpen, setMenuOpen] = useState<string | null>(null)

  useEffect(() => {
    loadStories()
  }, [])

  const loadStories = async () => {
    try {
      const res = await projectsApi.list()
      setStories(res.data)
    } catch {
      toast.error('Failed to load projects')
    } finally {
      setLoading(false)
    }
  }

  const createStory = async () => {
    if (!newTitle.trim()) return toast.error('Enter a title')
    setCreating(true)
    try {
      const res = await projectsApi.create(newTitle.trim())
      const story: Story = res.data
      setShowNewModal(false)
      setNewTitle('')
      router.push(`/projects/${story.story_id}/intake`)
    } catch {
      toast.error('Failed to create project')
    } finally {
      setCreating(false)
    }
  }

  const deleteStory = async (id: string) => {
    if (!confirm('Delete this project? This cannot be undone.')) return
    try {
      await projectsApi.delete(id)
      setStories((prev) => prev.filter((s) => s.story_id !== id))
      toast.success('Project deleted')
    } catch {
      toast.error('Failed to delete project')
    }
  }

  const filtered = stories.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase())
  )

  const totalWords = stories.reduce((a, s) => a + s.word_count, 0)

  return (
    <div className="min-h-screen bg-[#0d0f1a]">
      {/* Top Bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0d0f1a] border-b border-[#1f2440]">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Feather className="w-5 h-5 text-amber-500" />
            <span className="font-semibold text-sm">NarratIQ AI</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-[#9da3c8] hidden sm:block">
              {user?.username}
            </span>
            <button
              onClick={logout}
              className="text-[#5c6391] hover:text-[#9da3c8] p-2 rounded-lg transition-colors"
              title="Sign out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 pt-24 pb-16">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold">Your Manuscripts</h1>
            <p className="text-sm text-[#5c6391] mt-1">
              {stories.length} {stories.length === 1 ? 'project' : 'projects'} ·{' '}
              {totalWords >= 1000 ? `${(totalWords / 1000).toFixed(1)}k` : totalWords} total words
            </p>
          </div>
          <button
            onClick={() => setShowNewModal(true)}
            className="bg-amber-500 hover:bg-amber-600 text-black font-semibold px-5 py-2.5 rounded-xl text-sm flex items-center gap-2 transition-colors"
          >
            <Plus className="w-4 h-4" /> New Project
          </button>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Projects', value: stories.length, icon: BookOpen },
            { label: 'Total Words', value: totalWords >= 1000 ? `${(totalWords / 1000).toFixed(1)}k` : totalWords, icon: Edit3 },
            { label: 'Active', value: stories.filter((s) => s.status === 'active' || s.status === 'draft').length, icon: BarChart3 },
            { label: 'Archived', value: stories.filter((s) => s.status === 'archived').length, icon: Clock },
          ].map((stat) => (
            <div key={stat.label} className="bg-[#13162a] border border-[#1f2440] rounded-xl p-4">
              <div className="flex items-center gap-2 text-[#5c6391] mb-1">
                <stat.icon className="w-3.5 h-3.5" />
                <span className="text-xs">{stat.label}</span>
              </div>
              <div className="text-xl font-bold text-[#e8eaf6]">{stat.value}</div>
            </div>
          ))}
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5c6391]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search your manuscripts..."
            className="w-full bg-[#13162a] border border-[#1f2440] rounded-xl pl-9 pr-4 py-2.5 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-[#2e3454] transition-colors"
          />
        </div>

        {/* Stories grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <BookOpen className="w-12 h-12 text-[#2e3454] mx-auto mb-4" />
            <p className="text-[#5c6391] mb-2">
              {search ? 'No manuscripts match your search' : 'No manuscripts yet'}
            </p>
            {!search && (
              <button
                onClick={() => setShowNewModal(true)}
                className="text-amber-400 hover:text-amber-300 text-sm mt-2"
              >
                Create your first manuscript →
              </button>
            )}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((story) => (
              <div
                key={story.story_id}
                className="bg-[#13162a] border border-[#1f2440] rounded-xl p-5 hover:border-[#2e3454] transition-all group relative"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-8 h-8 bg-amber-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
                    <BookOpen className="w-4 h-4 text-amber-500" />
                  </div>
                  <div className="relative">
                    <button
                      onClick={() => setMenuOpen(menuOpen === story.story_id ? null : story.story_id)}
                      className="p-1.5 text-[#5c6391] hover:text-[#9da3c8] rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </button>
                    {menuOpen === story.story_id && (
                      <div className="absolute right-0 top-7 bg-[#1a1e36] border border-[#2e3454] rounded-lg py-1 w-40 z-10 shadow-xl">
                        <button
                          onClick={() => { setMenuOpen(null); router.push(`/projects/${story.story_id}`) }}
                          className="w-full text-left px-3 py-2 text-sm text-[#9da3c8] hover:bg-[#252a45] flex items-center gap-2"
                        >
                          <Edit3 className="w-3.5 h-3.5" /> Open Editor
                        </button>
                        <button
                          onClick={() => { setMenuOpen(null); deleteStory(story.story_id) }}
                          className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-[#252a45] flex items-center gap-2"
                        >
                          <Trash2 className="w-3.5 h-3.5" /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <Link href={`/projects/${story.story_id}`}>
                  <h3 className="font-semibold text-[#e8eaf6] mb-1 hover:text-amber-400 transition-colors line-clamp-2">
                    {story.title}
                  </h3>
                </Link>

                {story.description && (
                  <p className="text-xs text-[#5c6391] mb-3 line-clamp-2">{story.description}</p>
                )}

                <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#1f2440]">
                  <WordCountBadge count={story.word_count} />
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#5c6391]">
                      {formatDistanceToNow(new Date(story.updated_at), { addSuffix: true })}
                    </span>
                    <Link
                      href={`/projects/${story.story_id}`}
                      className="text-amber-500 hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* New Project Modal */}
      {showNewModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#13162a] border border-[#2e3454] rounded-2xl p-8 w-full max-w-md animate-slide-up">
            <h2 className="text-xl font-bold mb-1">New Manuscript</h2>
            <p className="text-sm text-[#9da3c8] mb-6">Give your story a working title to get started</p>
            <input
              autoFocus
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createStory()}
              placeholder="e.g. The House at the Edge of Everything"
              className="w-full bg-[#0d0f1a] border border-[#2e3454] rounded-xl px-4 py-3 text-sm text-[#e8eaf6] placeholder-[#3d4466] focus:outline-none focus:border-amber-500 transition-colors mb-5"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowNewModal(false)}
                className="flex-1 border border-[#2e3454] text-[#9da3c8] py-2.5 rounded-xl text-sm hover:border-[#3d4466] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={createStory}
                disabled={creating}
                className="flex-1 bg-amber-500 hover:bg-amber-600 text-black font-semibold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
              >
                {creating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Create & Set Up →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Click outside to close menu */}
      {menuOpen && (
        <div className="fixed inset-0 z-5" onClick={() => setMenuOpen(null)} />
      )}
    </div>
  )
}
