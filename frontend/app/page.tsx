'use client'

import Link from 'next/link'
import { BookOpen, Brain, Wand2, Camera, Globe, BarChart3, Shield, ChevronRight, Feather, Layers, Sparkles } from 'lucide-react'

const features = [
  { icon: Brain, title: 'Story Memory (RAG)', desc: 'Your manuscript lives in AI memory. Every suggestion, every transformation is grounded in YOUR established story.' },
  { icon: Sparkles, title: 'Genre Intelligence', desc: 'AI detects your genre, tone, and audience from your story idea — making every AI tool genre-aware from day one.' },
  { icon: Wand2, title: 'AI Plot Assistant', desc: 'Beat writer\'s block with context-aware suggestions. Not generic ideas — ideas that know your characters and world.' },
  { icon: Camera, title: 'Handwritten Notes OCR', desc: 'Photograph your notebook. OCR extracts the text, AI cleans it up, and it\'s injected directly into your project.' },
  { icon: Globe, title: 'Literary Translation', desc: '40+ languages with literary quality enhancement. Your prose maintains its soul across languages.' },
  { icon: BarChart3, title: 'Narrative Analytics', desc: 'Word count, readability scores, pacing metrics, emotion flow — understand your manuscript at a glance.' },
  { icon: Layers, title: 'Full Manuscript Pipeline', desc: 'Upload a 300-page novel. AI segments chapters, builds story memory, and makes everything searchable.' },
  { icon: Shield, title: 'Author Privacy First', desc: 'Self-hosted inference. Your story data never leaves your server. No third-party AI APIs touch your manuscript.' },
]

const tones = ['Dark', 'Suspenseful', 'Romantic', 'Epic', 'Melancholic', 'Humorous', 'Hopeful', 'Tense', 'Lyrical']

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0d0f1a] text-[#e8eaf6]">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-[#1f2440] bg-[#0d0f1a]/90 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Feather className="w-6 h-6 text-amber-500" />
            <span className="text-lg font-semibold tracking-tight">NarratIQ AI</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-[#9da3c8] hover:text-white text-sm transition-colors px-4 py-2">
              Sign In
            </Link>
            <Link href="/register" className="bg-amber-500 hover:bg-amber-600 text-black text-sm font-semibold px-5 py-2 rounded-lg transition-colors">
              Start Writing Free
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-24 px-6 text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-radial from-amber-500/5 via-transparent to-transparent" />
        <div className="max-w-4xl mx-auto relative">
          <div className="inline-flex items-center gap-2 bg-[#1a1e36] border border-[#2e3454] rounded-full px-4 py-1.5 text-sm text-amber-400 mb-8">
            <Sparkles className="w-4 h-4" />
            AI-Powered Long-Form Storytelling Platform v3.0
          </div>
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight mb-6 leading-[1.1]">
            Write Longer.{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-600">
              Write Better.
            </span>
          </h1>
          <p className="text-xl text-[#9da3c8] mb-4 max-w-2xl mx-auto leading-relaxed">
            The AI writing studio built exclusively for novelists. Story memory, genre intelligence,
            plot assistance, and literary transformation — all in one place.
          </p>
          <p className="text-sm text-[#5c6391] mb-10">
            Your story data never leaves your server. Complete author privacy.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/register"
              className="bg-amber-500 hover:bg-amber-600 text-black font-bold px-8 py-4 rounded-xl text-lg transition-all hover:scale-[1.02] flex items-center justify-center gap-2"
            >
              Start Your Manuscript <ChevronRight className="w-5 h-5" />
            </Link>
            <Link
              href="/login"
              className="border border-[#2e3454] hover:border-[#3d4466] text-[#9da3c8] hover:text-white px-8 py-4 rounded-xl text-lg transition-all"
            >
              Sign In
            </Link>
          </div>
        </div>
      </section>

      {/* Tone strip */}
      <section className="py-6 border-y border-[#1f2440] overflow-hidden bg-[#0f1220]">
        <div className="flex gap-3 animate-pulse-scroll px-6 flex-wrap justify-center">
          {tones.map((tone) => (
            <span key={tone} className="px-4 py-1.5 rounded-full border border-[#2e3454] text-[#9da3c8] text-sm whitespace-nowrap">
              {tone} Tone
            </span>
          ))}
          <span className="px-4 py-1.5 rounded-full border border-amber-500/40 text-amber-400 text-sm">+ 40 Languages</span>
          <span className="px-4 py-1.5 rounded-full border border-[#2e3454] text-[#9da3c8] text-sm">9 Emotion Modes</span>
          <span className="px-4 py-1.5 rounded-full border border-[#2e3454] text-[#9da3c8] text-sm">3 Age Audiences</span>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">Everything a Serious Author Needs</h2>
            <p className="text-[#9da3c8] max-w-xl mx-auto">
              Built from first principles for the demands of long-form manuscript creation.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {features.map((f) => (
              <div key={f.title} className="bg-[#13162a] border border-[#1f2440] rounded-xl p-6 hover:border-[#2e3454] transition-all hover:-translate-y-1">
                <div className="w-10 h-10 bg-amber-500/10 rounded-lg flex items-center justify-center mb-4">
                  <f.icon className="w-5 h-5 text-amber-500" />
                </div>
                <h3 className="font-semibold mb-2 text-[#e8eaf6]">{f.title}</h3>
                <p className="text-sm text-[#9da3c8] leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Problem/Solution */}
      <section className="py-20 px-6 bg-[#0f1220]">
        <div className="max-w-5xl mx-auto">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl font-bold mb-6">The Problem with Every Other Tool</h2>
              <ul className="space-y-4">
                {[
                  'Grammar tools fix surface errors but have zero story context',
                  'ChatGPT/Claude have no persistent story memory — every session starts from zero',
                  'Scrivener is purely organizational — zero AI intelligence',
                  'Professional developmental editing costs $2,000–$10,000 per manuscript',
                  'No platform supports the full workflow from intake to export',
                ].map((p) => (
                  <li key={p} className="flex gap-3 text-[#9da3c8] text-sm">
                    <span className="text-red-400 mt-0.5 flex-shrink-0">✗</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2 className="text-3xl font-bold mb-6 text-amber-400">The NarratIQ Difference</h2>
              <ul className="space-y-4">
                {[
                  'Story memory that persists across every session and every chapter',
                  'Genre-aware AI that knows your tone, audience, and conflict from day one',
                  'Plot assistance grounded in YOUR established story — not generic ideas',
                  'Literary-quality transformations at paragraph, chapter, and manuscript scale',
                  'Complete workflow: intake → memory → write → assist → analyze → export',
                ].map((p) => (
                  <li key={p} className="flex gap-3 text-[#e8eaf6] text-sm">
                    <span className="text-amber-400 mt-0.5 flex-shrink-0">✓</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-4xl font-bold mb-4">Your manuscript deserves better.</h2>
          <p className="text-[#9da3c8] mb-10">Join the platform that treats your novel as a novel, not a text snippet.</p>
          <Link
            href="/register"
            className="inline-flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-black font-bold px-10 py-4 rounded-xl text-lg transition-all hover:scale-[1.02]"
          >
            <BookOpen className="w-5 h-5" />
            Start Writing — It's Free
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#1f2440] py-10 px-6 text-center text-sm text-[#5c6391]">
        <div className="flex items-center justify-center gap-2 mb-2">
          <Feather className="w-4 h-4 text-amber-500" />
          <span className="text-[#9da3c8] font-medium">NarratIQ AI</span>
        </div>
        <p>AI-Powered Long-Form Storytelling Platform v3.0 — Self-hosted. Author privacy first.</p>
      </footer>
    </div>
  )
}
