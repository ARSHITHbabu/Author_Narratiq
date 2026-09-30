import Link from 'next/link'
import { Feather } from 'lucide-react'

// Published data retention and deletion policy (Stage 10, task 10.6).
// The engineering source of truth is docs/policies/data-retention-and-deletion.md;
// this page states the same rules in author terms. Keep the two in step.
export const metadata = { title: 'Data policy — NarratIQ AI' }

const rows: [string, string][] = [
  ['Your manuscripts, chapters, characters, notes and Story Bible',
   'Kept until you delete them. Deleting a chapter or a manuscript removes it at once, together with everything NarratIQ derived from it (search index, summaries, character mentions).'],
  ['Uploaded page photos (OCR) and audio recordings',
   'The file is deleted 24 hours after you confirm the extracted text, or after 72 hours if you never confirm it. The text you chose to keep stays in your notes.'],
  ['Saved AI versions (pins)',
   'Expire automatically: 7 days on the free plan, 30 on basic, 90 on pro and 180 on studio. They are never included in backups.'],
  ['Unsaved AI results',
   'Never stored on our servers. They exist only in your browser until you save or discard them.'],
  ['Backups',
   'The database is backed up every hour to private storage in our hosting environment. Hourly backups are kept for 24 hours and one daily backup for 7 days, then they are deleted automatically.'],
  ['Error reports',
   'Technical error records never contain your writing, your email address or your password. They are deleted after 30 days.'],
  ['Signed-out sessions',
   'A record that a session was signed out is kept only until that session would have expired anyway.'],
]

export default function DataPolicyPage() {
  return (
    <main className="min-h-screen bg-[#0d0f1a]">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Link href="/" className="inline-flex items-center gap-2 mb-10 text-sm">
          <Feather className="w-5 h-5 text-amber-500" aria-hidden /> NarratIQ AI
        </Link>
        <h1 className="text-2xl font-bold mb-2">How long we keep your data, and how to delete it</h1>
        <p className="text-sm text-[#9da3c8] mb-8">
          Your unpublished work is yours. NarratIQ keeps it only to provide the service, and you can delete it at any time.
        </p>

        <section aria-labelledby="keep" className="mb-10">
          <h2 id="keep" className="text-lg font-semibold mb-4">What we keep</h2>
          <dl className="space-y-4">
            {rows.map(([what, rule]) => (
              <div key={what} className="bg-[#13162a] border border-[#1f2440] rounded-xl p-4">
                <dt className="text-sm font-medium text-[#e8eaf6] mb-1">{what}</dt>
                <dd className="text-sm text-[#9da3c8]">{rule}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="delete" className="mb-10">
          <h2 id="delete" className="text-lg font-semibold mb-3">Deleting your account</h2>
          <p className="text-sm text-[#9da3c8] mb-3">
            Go to <strong>Account</strong> (from your manuscripts page) and choose <strong>Delete account</strong>. After you
            confirm with your password, your account and everything in it are removed immediately and permanently:
            manuscripts, chapters, characters, notes, Story Bibles, saved AI versions, voice sessions, uploaded images and
            recordings, and every search-index entry made from your writing. You are signed out on every device.
          </p>
          <p className="text-sm text-[#9da3c8]">
            What deletion cannot reach at once: copies inside backups made before you deleted your account. Those backups
            expire on the schedule above, so no copy of your data remains after at most 7 days.
          </p>
        </section>

        <section aria-labelledby="sessions">
          <h2 id="sessions" className="text-lg font-semibold mb-3">Signing out and changing your password</h2>
          <p className="text-sm text-[#9da3c8]">
            Signing out ends the session on that device only. Changing your password signs you out on every other device.
          </p>
        </section>
      </div>
    </main>
  )
}
