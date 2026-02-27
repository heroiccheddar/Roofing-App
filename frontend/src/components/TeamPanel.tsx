import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useOrg, useCreateOrg, useJoinOrg, useLeaveOrg } from '../hooks/useOrg'

export default function TeamPanel() {
  const darkMode = useAppStore((s) => s.darkMode)
  const showTeamPins = useAppStore((s) => s.showTeamPins)
  const setShowTeamPins = useAppStore((s) => s.setShowTeamPins)
  const user = useAppStore((s) => s.user)

  const { data: org, isError: noOrg, isLoading: orgLoading } = useOrg()
  const createOrgMut = useCreateOrg()
  const joinOrgMut = useJoinOrg()
  const leaveOrgMut = useLeaveOrg()

  const [expanded, setExpanded] = useState(false)
  const [mode, setMode] = useState<'idle' | 'create' | 'join'>('idle')
  const [name, setName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [copied, setCopied] = useState(false)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'

  const handleCreate = () => {
    if (!name.trim()) return
    createOrgMut.mutate({ name: name.trim() }, {
      onSuccess: () => { setMode('idle'); setName('') },
    })
  }

  const handleJoin = () => {
    if (!inviteCode.trim()) return
    joinOrgMut.mutate({ invite_code: inviteCode.trim() }, {
      onSuccess: () => { setMode('idle'); setInviteCode('') },
    })
  }

  const handleCopy = () => {
    if (org?.invite_code) {
      navigator.clipboard.writeText(org.invite_code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const currentRole = org?.members?.find((m) => m.id === user?.id)?.org_role

  // Still loading — render nothing to avoid flash
  if (orgLoading) return null

  const headerLabel = org ? `Team — ${org.name}` : 'Team'

  return (
    <div style={{ borderBottom: `1px solid ${borderColor}` }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: textPrimary,
          fontSize: 14,
          fontWeight: 700,
        }}
      >
        <span>{headerLabel}</span>
        <span style={{ fontSize: 11, color: textSecondary }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 12px' }}>
          {/* No org — show create/join UI */}
          {noOrg && (
            <>
              {mode === 'idle' && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => setMode('create')}
                    style={{
                      flex: 1,
                      padding: '7px 0',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: 'transparent',
                      color: textPrimary,
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Create Team
                  </button>
                  <button
                    onClick={() => setMode('join')}
                    style={{
                      flex: 1,
                      padding: '7px 0',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: 'transparent',
                      color: textPrimary,
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Join Team
                  </button>
                </div>
              )}

              {mode === 'create' && (
                <div>
                  <input
                    type="text"
                    placeholder="Team name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: darkMode ? '#0f172a' : '#ffffff',
                      color: textPrimary,
                      fontSize: 13,
                      boxSizing: 'border-box',
                      marginBottom: 8,
                    }}
                  />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={handleCreate}
                      disabled={!name.trim() || createOrgMut.isPending}
                      style={{
                        flex: 2,
                        padding: '7px 0',
                        borderRadius: 8,
                        border: 'none',
                        background: !name.trim() || createOrgMut.isPending ? (darkMode ? '#334155' : '#e2e8f0') : '#2563eb',
                        color: !name.trim() || createOrgMut.isPending ? textSecondary : '#ffffff',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: !name.trim() || createOrgMut.isPending ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {createOrgMut.isPending ? 'Creating...' : 'Create'}
                    </button>
                    <button
                      onClick={() => { setMode('idle'); setName('') }}
                      style={{
                        flex: 1,
                        padding: '7px 0',
                        borderRadius: 8,
                        border: `1px solid ${borderColor}`,
                        background: 'transparent',
                        color: textSecondary,
                        fontSize: 13,
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {mode === 'join' && (
                <div>
                  <input
                    type="text"
                    placeholder="Invite code"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: darkMode ? '#0f172a' : '#ffffff',
                      color: textPrimary,
                      fontSize: 13,
                      boxSizing: 'border-box',
                      marginBottom: 8,
                    }}
                  />
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={handleJoin}
                      disabled={!inviteCode.trim() || joinOrgMut.isPending}
                      style={{
                        flex: 2,
                        padding: '7px 0',
                        borderRadius: 8,
                        border: 'none',
                        background: !inviteCode.trim() || joinOrgMut.isPending ? (darkMode ? '#334155' : '#e2e8f0') : '#2563eb',
                        color: !inviteCode.trim() || joinOrgMut.isPending ? textSecondary : '#ffffff',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: !inviteCode.trim() || joinOrgMut.isPending ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {joinOrgMut.isPending ? 'Joining...' : 'Join'}
                    </button>
                    <button
                      onClick={() => { setMode('idle'); setInviteCode('') }}
                      style={{
                        flex: 1,
                        padding: '7px 0',
                        borderRadius: 8,
                        border: `1px solid ${borderColor}`,
                        background: 'transparent',
                        color: textSecondary,
                        fontSize: 13,
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* In org — show org info */}
          {org && (
            <>
              {/* Invite code row */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 10,
                padding: '8px 10px',
                borderRadius: 8,
                border: `1px solid ${borderColor}`,
                background: darkMode ? '#0f172a' : '#f8fafc',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, color: textSecondary, marginBottom: 2 }}>Invite code</div>
                  <div style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: textPrimary,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {org.invite_code}
                  </div>
                </div>
                <button
                  onClick={handleCopy}
                  style={{
                    padding: '5px 10px',
                    borderRadius: 6,
                    border: `1px solid ${borderColor}`,
                    background: 'transparent',
                    color: copied ? '#16a34a' : textSecondary,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    flexShrink: 0,
                  }}
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>

              {/* Show Team Pins toggle */}
              <button
                onClick={() => setShowTeamPins(!showTeamPins)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: showTeamPins
                    ? '2px solid #2563eb'
                    : `1px solid ${borderColor}`,
                  background: showTeamPins ? '#2563eb18' : 'transparent',
                  color: showTeamPins ? '#2563eb' : textPrimary,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  marginBottom: 10,
                  transition: 'all 0.12s',
                }}
              >
                <span>Show Team Pins</span>
                <span style={{
                  width: 32,
                  height: 18,
                  borderRadius: 9,
                  background: showTeamPins ? '#2563eb' : (darkMode ? '#334155' : '#cbd5e1'),
                  position: 'relative',
                  flexShrink: 0,
                  transition: 'background 0.12s',
                }}>
                  <span style={{
                    position: 'absolute',
                    top: 2,
                    left: showTeamPins ? 16 : 2,
                    width: 14,
                    height: 14,
                    borderRadius: '50%',
                    background: '#ffffff',
                    transition: 'left 0.12s',
                  }} />
                </span>
              </button>

              {/* Member list */}
              <div style={{ fontSize: 11, color: textSecondary, marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Members
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
                {org.members.map((member) => (
                  <div
                    key={member.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '7px 10px',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: darkMode ? '#0f172a' : '#f8fafc',
                      gap: 8,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: textPrimary,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}>
                        {member.company_name}
                      </div>
                      <div style={{
                        fontSize: 11,
                        color: textSecondary,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}>
                        {member.email}
                      </div>
                    </div>
                    <span style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '2px 7px',
                      borderRadius: 4,
                      background: member.org_role === 'owner' ? '#f59e0b18' : (darkMode ? '#334155' : '#e2e8f0'),
                      color: member.org_role === 'owner' ? '#f59e0b' : textSecondary,
                      textTransform: 'uppercase',
                      flexShrink: 0,
                    }}>
                      {member.org_role}
                    </span>
                  </div>
                ))}
              </div>

              {/* Leave button — only for members, not owner */}
              {currentRole === 'member' && (
                <button
                  onClick={() => leaveOrgMut.mutate()}
                  disabled={leaveOrgMut.isPending}
                  style={{
                    width: '100%',
                    padding: '7px 0',
                    borderRadius: 8,
                    border: '1px solid #ef4444',
                    background: 'transparent',
                    color: '#ef4444',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: leaveOrgMut.isPending ? 'wait' : 'pointer',
                    opacity: leaveOrgMut.isPending ? 0.7 : 1,
                  }}
                >
                  {leaveOrgMut.isPending ? 'Leaving...' : 'Leave Team'}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
