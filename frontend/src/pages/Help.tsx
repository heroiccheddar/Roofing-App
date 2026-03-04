/**
 * Help — in-app feature guide for RoofIQ.
 *
 * Static content page explaining every feature in plain language,
 * organized by workflow. Follows the Settings.tsx full-screen overlay pattern.
 */

import { useNavigate } from 'react-router-dom'

export default function Help() {
  const navigate = useNavigate()

  const cardStyle: React.CSSProperties = {
    background: 'var(--card-bg)',
    border: '1px solid var(--card-border)',
    borderRadius: 12,
    padding: '20px',
    marginBottom: 20,
  }

  const titleStyle: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: '0 0 12px',
  }

  const bulletStyle: React.CSSProperties = {
    fontSize: 13,
    lineHeight: '1.6',
    color: 'var(--text-secondary)',
    margin: '0 0 6px',
    paddingLeft: 16,
    position: 'relative',
  }

  const dotStyle: React.CSSProperties = {
    position: 'absolute',
    left: 0,
    top: 0,
    color: 'var(--accent-blue)',
    fontWeight: 700,
  }

  function Bullet({ children }: { children: React.ReactNode }) {
    return (
      <p style={bulletStyle}>
        <span style={dotStyle}>&bull;</span>
        {children}
      </p>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 200,
      background: 'var(--bg-primary)',
      color: 'var(--text-primary)',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '1px solid var(--card-border)',
        background: 'var(--bg-primary)',
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--accent-blue)',
            fontSize: 15,
            fontWeight: 600,
            cursor: 'pointer',
            padding: '8px 12px',
            minHeight: 44,
          }}
        >
          &larr; Back
        </button>
        <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>
          Help Guide
        </span>
        <div style={{ width: 60 }} />
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '20px 16px' }}>

          {/* Intro */}
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: 20 }}>
            RoofIQ helps you find, track, and close roofing leads. This guide
            walks through every feature so you can get the most out of the app.
          </p>

          {/* 1. Getting Started */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Getting Started</h2>
            <Bullet>
              <strong>Set your service area</strong> in Settings. Enter your city
              and state, pick a radius, and RoofIQ will focus storm alerts and
              zone data on the area you actually work.
            </Bullet>
            <Bullet>
              <strong>Storm alerts</strong> are automatic. When severe weather
              hits your service area, RoofIQ scores the affected zones so you
              know where to canvass first.
            </Bullet>
            <Bullet>
              <strong>The map</strong> is your home base. It shows your lead
              pins, storm zones, and heatmap layers all in one view.
            </Bullet>
          </div>

          {/* 2. Lead Pins & Canvassing */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Lead Pins &amp; Canvassing</h2>
            <Bullet>
              <strong>Drop a pin</strong> by tapping the pin-drop button, then
              tapping a location on the map. You'll be asked to set a
              disposition right away.
            </Bullet>
            <Bullet>
              <strong>Dispositions</strong> track where each lead stands:
              Not Home, Callback, Interested, Inspection Set, Contract Signed,
              or Not Interested. Tap a pin to change its disposition at any time.
            </Bullet>
            <Bullet>
              <strong>Contact info</strong> (name, phone, email) can be added
              when you create or update a pin. This is saved on the pin and
              included in CSV exports.
            </Bullet>
            <Bullet>
              <strong>Lead source</strong> tracks where the lead came from —
              Door Knock, Referral, Website, Storm Canvass, or Other. Pick one
              when creating a pin to see which channels produce the best results
              in your analytics.
            </Bullet>
            <Bullet>
              <strong>Photos</strong> can be attached to any pin. Tap the camera
              icon in the pin detail to capture roof damage, before/after shots,
              or anything else you need on file.
            </Bullet>
            <Bullet>
              <strong>Notes</strong> are freeform text on each pin — use them
              for details the homeowner mentioned, roof condition observations,
              or next-step reminders.
            </Bullet>
          </div>

          {/* 3. Property Intelligence */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Property Intelligence</h2>
            <Bullet>
              <strong>Property data</strong> loads automatically when you drop
              a pin. RoofIQ pulls public parcel records including owner name,
              year built, roof age, square footage, and assessed value.
            </Bullet>
            <Bullet>
              <strong>Roof measurements</strong> use Google's satellite imagery
              to calculate total roof area, number of facets, and average pitch.
              Tap "Fetch Roof Data" on a pin's property card to load it.
            </Bullet>
            <Bullet>
              <strong>Steep pitch warnings</strong> appear when the average roof
              pitch exceeds 30 degrees. Pitches above 37 degrees are flagged as
              "very steep" — both affect labor costs.
            </Bullet>
          </div>

          {/* 4. Estimates */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Estimates</h2>
            <Bullet>
              <strong>Create an estimate</strong> from any pin's detail view.
              Add line items with description, quantity, unit, and unit price.
              Totals calculate automatically.
            </Bullet>
            <Bullet>
              <strong>Auto-fill from roof data</strong> generates starter line
              items (tear-off, underlayment, shingles, drip edge, ridge cap)
              using the actual roof square footage. If the pitch is steep, a
              surcharge line is added automatically.
            </Bullet>
            <Bullet>
              <strong>Status tracking</strong> lets you mark estimates as Draft,
              Sent, Accepted, or Declined. The deal value on the pin updates
              when you save an estimate.
            </Bullet>
            <Bullet>
              <strong>Print</strong> any estimate to share with the homeowner
              or your office.
            </Bullet>
          </div>

          {/* 5. Pipeline Board */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Pipeline Board</h2>
            <Bullet>
              <strong>Kanban view</strong> shows all your leads organized into
              columns by disposition. Each column shows the count and total
              deal value.
            </Bullet>
            <Bullet>
              <strong>Move leads</strong> by dragging cards between columns on
              desktop. On mobile, tap a card to reveal disposition buttons and
              tap the one you want.
            </Bullet>
            <Bullet>
              <strong>Team view</strong> toggle shows pins from your entire
              organization, not just yours.
            </Bullet>
          </div>

          {/* 6. Calendar */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Calendar</h2>
            <Bullet>
              <strong>Day and week views</strong> display all leads with a
              scheduled callback date. Switch between views with the Day/Week
              toggle.
            </Bullet>
            <Bullet>
              <strong>Overdue callbacks</strong> are highlighted so you never
              miss a follow-up.
            </Bullet>
            <Bullet>
              <strong>Tap an event</strong> to jump back to the map and
              select that pin.
            </Bullet>
          </div>

          {/* 7. Communication Log */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Communication Log</h2>
            <Bullet>
              <strong>Log interactions</strong> on any pin — calls, texts,
              emails, visits, or general notes. Each entry is timestamped
              and displayed in the pin's activity timeline.
            </Bullet>
            <Bullet>
              <strong>Activity types</strong> are color-coded pills so you can
              quickly scan a pin's history and see how you've been engaging
              the homeowner.
            </Bullet>
          </div>

          {/* 8. Follow-Up Queue */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Follow-Up Queue</h2>
            <Bullet>
              <strong>Pending callbacks</strong> are listed in order of urgency.
              Overdue items float to the top.
            </Bullet>
            <Bullet>
              <strong>Route optimization</strong> builds a driving route through
              your follow-ups using the Route tab on the map. Great for
              planning an afternoon of callbacks.
            </Bullet>
          </div>

          {/* 9. Storm Zones */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Storm Zones</h2>
            <Bullet>
              <strong>Zone scoring</strong> rates areas by storm severity so you
              can prioritize canvassing where damage is most likely.
            </Bullet>
            <Bullet>
              <strong>Heatmap layers</strong> toggle between pin density and
              zone scores on the map for a visual overview of your territory.
            </Bullet>
            <Bullet>
              <strong>Zone detail</strong> pages show neighborhood breakdowns,
              census tract data, and exposure analysis for deeper research.
            </Bullet>
          </div>

          {/* 10. Analytics */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Analytics</h2>
            <Bullet>
              <strong>Sales funnel</strong> shows how your leads progress from
              "Pins Dropped" through "Contract Signed" so you can spot where
              leads are falling off.
            </Bullet>
            <Bullet>
              <strong>KPIs</strong> include total pins, conversion rate,
              pending callbacks, inspections set, and average pins per day.
            </Bullet>
            <Bullet>
              <strong>Lead source breakdown</strong> shows which channels
              (door knocks, referrals, website, etc.) are generating the most
              leads.
            </Bullet>
            <Bullet>
              <strong>Time periods</strong> — switch between This Week, This
              Month, and All Time to track performance over different windows.
            </Bullet>
          </div>

          {/* 11. Team & Collaboration */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Team &amp; Collaboration</h2>
            <Bullet>
              <strong>Invite teammates</strong> from Settings using your
              organization's invite code. Everyone on the team shares the same
              zones, pins, and pipeline data.
            </Bullet>
            <Bullet>
              <strong>Leaderboard</strong> ranks team members by pins dropped
              and contracts signed for the current period.
            </Bullet>
            <Bullet>
              <strong>Team view</strong> is available on the Pipeline Board,
              Calendar, and CSV export — toggle it to see everyone's activity.
            </Bullet>
          </div>

          {/* 12. Settings */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Settings</h2>
            <Bullet>
              <strong>Profile</strong> — update your company name and phone
              number.
            </Bullet>
            <Bullet>
              <strong>Service area</strong> — set your city, state, and radius
              to receive relevant storm alerts.
            </Bullet>
            <Bullet>
              <strong>Alert preferences</strong> — choose minimum score
              thresholds, hail-only mode, notification channels (push and
              email), and quiet hours.
            </Bullet>
            <Bullet>
              <strong>Dark mode</strong> — toggle between light and dark themes.
            </Bullet>
          </div>

          {/* 13. Tips */}
          <div style={cardStyle}>
            <h2 style={titleStyle}>Tips &amp; Shortcuts</h2>
            <Bullet>
              <strong>Offline mode</strong> — RoofIQ works offline. Pins and
              changes you make without internet are saved locally and sync
              automatically when you reconnect.
            </Bullet>
            <Bullet>
              <strong>CSV export</strong> — download all your leads as a
              spreadsheet from the Lead Pins panel. Includes contacts,
              dispositions, lead source, coordinates, and timestamps.
            </Bullet>
            <Bullet>
              <strong>Pin drop shortcut</strong> — long-press on the map to
              quickly drop a pin without toggling pin-drop mode.
            </Bullet>
          </div>

          {/* Footer spacer */}
          <div style={{ height: 40 }} />
        </div>
      </div>
    </div>
  )
}
