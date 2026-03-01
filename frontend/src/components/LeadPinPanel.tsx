/**
 * LeadPinPanel — UI for the Lead Pins + Dispositions feature.
 *
 * Responsibilities:
 *  - Pin-drop mode toggle button
 *  - Disposition picker modal (new pin or update existing)
 *  - Pin list for current viewport
 *  - Pin detail with activity timeline
 *  - Delete pin with confirmation
 */

import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { exportLeadsCsv } from '../api/client'
import { useLeadPins, useLeadPinDetail, useUpdateLeadPin, useDeleteLeadPin, useLeadPinActivities, useCreatePinActivity, useProperty } from '../hooks/useLeadPins'
import { useEstimates, useCreateEstimate, useUpdateEstimate, useDeleteEstimate } from '../hooks/useEstimates'
import { DispositionBadge, DISPOSITION_COLORS, DISPOSITION_LABELS } from './ZoneDetailHelpers'
import PhotoGallery from './PhotoGallery'
import type { LeadPinDisposition, LeadPinResponse, EstimateResponse, LineItem } from '../types/api'

// ===== Helpers =====

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString()
}

const DISPOSITION_ORDER: LeadPinDisposition[] = [
  'not_home',
  'callback',
  'interested',
  'inspection_set',
  'contract_signed',
  'not_interested',
]

// ===== Disposition Picker =====

interface DispositionPickerProps {
  initialDisposition?: LeadPinDisposition
  initialNotes?: string
  initialCallbackDate?: string
  initialContactName?: string
  initialContactPhone?: string
  initialContactEmail?: string
  title: string
  onConfirm: (disposition: LeadPinDisposition, notes: string, callbackDate?: string, contactName?: string, contactPhone?: string, contactEmail?: string) => void
  onCancel: () => void
  isLoading?: boolean
}

export function DispositionPicker({
  initialDisposition,
  initialNotes = '',
  initialCallbackDate,
  initialContactName,
  initialContactPhone,
  initialContactEmail,
  title,
  onConfirm,
  onCancel,
  isLoading = false,
}: DispositionPickerProps) {
  const [selected, setSelected] = useState<LeadPinDisposition>(
    initialDisposition ?? 'not_home',
  )
  const [notes, setNotes] = useState(initialNotes)
  const [callbackDate, setCallbackDate] = useState(initialCallbackDate || '')
  const [contactName, setContactName] = useState(initialContactName || '')
  const [contactPhone, setContactPhone] = useState(initialContactPhone || '')
  const [contactEmail, setContactEmail] = useState(initialContactEmail || '')
  const darkMode = useAppStore((s) => s.darkMode)

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.45)',
      zIndex: 200,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '16px',
    }}>
      <div style={{
        background: darkMode ? '#1e293b' : '#ffffff',
        borderRadius: 12,
        padding: 20,
        width: '100%',
        maxWidth: 360,
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <h3 style={{
          margin: '0 0 16px',
          fontSize: 16,
          fontWeight: 700,
          color: darkMode ? '#f1f5f9' : '#0f172a',
        }}>
          {title}
        </h3>

        {/* 2x3 disposition grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 8,
          marginBottom: 16,
        }}>
          {DISPOSITION_ORDER.map((d) => {
            const color = DISPOSITION_COLORS[d]
            const isActive = selected === d
            return (
              <button
                key={d}
                onClick={() => setSelected(d)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: isActive ? `2px solid ${color}` : `2px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
                  background: isActive ? `${color}18` : (darkMode ? '#0f172a' : '#f8fafc'),
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? color : (darkMode ? '#94a3b8' : '#475569'),
                  transition: 'all 0.12s',
                  textAlign: 'left',
                }}
              >
                <span style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  backgroundColor: color,
                  flexShrink: 0,
                }} />
                {DISPOSITION_LABELS[d]}
              </button>
            )
          })}
        </div>

        {/* Callback date — only shown when disposition is 'callback' */}
        {selected === 'callback' && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, color: darkMode ? '#94a3b8' : '#64748b', display: 'block', marginBottom: 4 }}>
              Follow-up date (optional)
            </label>
            <input
              type="datetime-local"
              value={callbackDate}
              onChange={(e) => setCallbackDate(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 8,
                border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
                background: darkMode ? '#0f172a' : '#ffffff',
                color: darkMode ? '#f1f5f9' : '#0f172a',
                fontSize: 13,
                boxSizing: 'border-box',
              }}
            />
          </div>
        )}

        {/* Contact info fields */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: darkMode ? '#94a3b8' : '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
            Contact Info
          </div>
          <input
            type="text"
            placeholder="Name"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`, background: darkMode ? '#0f172a' : '#f8fafc', color: darkMode ? '#f1f5f9' : '#0f172a', fontSize: 13, marginBottom: 6, boxSizing: 'border-box' }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              type="tel"
              placeholder="Phone"
              value={contactPhone}
              onChange={(e) => setContactPhone(e.target.value)}
              style={{ flex: 1, padding: '8px 10px', borderRadius: 6, border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`, background: darkMode ? '#0f172a' : '#f8fafc', color: darkMode ? '#f1f5f9' : '#0f172a', fontSize: 13, boxSizing: 'border-box' }}
            />
            <input
              type="email"
              placeholder="Email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              style={{ flex: 1, padding: '8px 10px', borderRadius: 6, border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`, background: darkMode ? '#0f172a' : '#f8fafc', color: darkMode ? '#f1f5f9' : '#0f172a', fontSize: 13, boxSizing: 'border-box' }}
            />
          </div>
        </div>

        {/* Notes textarea */}
        <textarea
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 1000))}
          maxLength={1000}
          rows={3}
          style={{
            width: '100%',
            padding: '8px 10px',
            borderRadius: 8,
            border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
            background: darkMode ? '#0f172a' : '#f8fafc',
            color: darkMode ? '#f1f5f9' : '#0f172a',
            fontSize: 13,
            resize: 'vertical',
            boxSizing: 'border-box',
            marginBottom: 4,
            fontFamily: 'inherit',
          }}
        />
        <div style={{
          fontSize: 11,
          color: darkMode ? '#475569' : '#94a3b8',
          textAlign: 'right',
          marginBottom: 16,
        }}>
          {notes.length}/1000
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1,
              padding: '10px 0',
              borderRadius: 8,
              border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
              background: 'transparent',
              color: darkMode ? '#94a3b8' : '#64748b',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(selected, notes, callbackDate || undefined, contactName || undefined, contactPhone || undefined, contactEmail || undefined)}
            disabled={isLoading}
            style={{
              flex: 2,
              padding: '10px 0',
              borderRadius: 8,
              border: 'none',
              background: DISPOSITION_COLORS[selected],
              color: '#ffffff',
              fontSize: 14,
              fontWeight: 700,
              cursor: isLoading ? 'wait' : 'pointer',
              opacity: isLoading ? 0.7 : 1,
            }}
          >
            {isLoading ? 'Saving...' : 'Save Pin'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== Estimate Helpers =====

const ESTIMATE_STATUS_COLORS: Record<string, string> = {
  draft: '#64748b',
  sent: '#2563eb',
  accepted: '#16a34a',
  declined: '#ef4444',
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function blankLineItem(): LineItem {
  return { description: '', quantity: 1, unit: 'sq', unit_price: 0, total: 0 }
}

function computeTotals(items: LineItem[], taxRate: number): { subtotal: number; total: number } {
  const subtotal = items.reduce((sum, it) => sum + it.total, 0)
  return { subtotal, total: subtotal * (1 + taxRate) }
}

// ===== Estimate Builder (inline form) =====

interface EstimateBuilderProps {
  pinId: string
  initial?: EstimateResponse
  onSaved: () => void
  onCancel: () => void
}

function EstimateBuilder({ pinId, initial, onSaved, onCancel }: EstimateBuilderProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const createEstimate = useCreateEstimate()
  const updateEstimate = useUpdateEstimate()

  const [lineItems, setLineItems] = useState<LineItem[]>(
    initial?.line_items?.length ? initial.line_items : [blankLineItem()],
  )
  const [taxRateStr, setTaxRateStr] = useState(
    initial ? String(initial.tax_rate * 100) : '0',
  )
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [status, setStatus] = useState(initial?.status ?? 'draft')

  const taxRate = parseFloat(taxRateStr) / 100 || 0
  const { subtotal, total } = computeTotals(lineItems, taxRate)

  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'
  const inputBg = darkMode ? '#0f172a' : '#ffffff'

  function updateItem(index: number, field: keyof LineItem, value: string | number) {
    setLineItems((prev) => {
      const next = prev.map((it, i) => {
        if (i !== index) return it
        const updated = { ...it, [field]: value }
        updated.total = Math.round(updated.quantity * updated.unit_price * 100) / 100
        return updated
      })
      return next
    })
  }

  function addItem() {
    setLineItems((prev) => [...prev, blankLineItem()])
  }

  function removeItem(index: number) {
    setLineItems((prev) => prev.filter((_, i) => i !== index))
  }

  function handleSave() {
    const sanitizedItems = lineItems.map((it) => ({
      ...it,
      total: Math.round(it.quantity * it.unit_price * 100) / 100,
    }))

    if (initial) {
      updateEstimate.mutate(
        { estimateId: initial.id, data: { line_items: sanitizedItems, tax_rate: taxRate, notes: notes || undefined, status } },
        { onSuccess: onSaved },
      )
    } else {
      createEstimate.mutate(
        { lead_pin_id: pinId, line_items: sanitizedItems, tax_rate: taxRate, notes: notes || undefined, status },
        { onSuccess: onSaved },
      )
    }
  }

  const isSaving = createEstimate.isPending || updateEstimate.isPending
  const inputStyle: React.CSSProperties = {
    padding: '5px 7px',
    borderRadius: 6,
    border: `1px solid ${borderColor}`,
    background: inputBg,
    color: textPrimary,
    fontSize: 12,
    boxSizing: 'border-box',
    width: '100%',
  }

  return (
    <div style={{
      padding: 12,
      borderRadius: 8,
      border: `1px solid ${borderColor}`,
      background: bgSecondary,
      marginTop: 8,
    }}>
      {/* Status selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: textSecondary, flexShrink: 0 }}>Status:</span>
        {(['draft', 'sent', 'accepted', 'declined'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            style={{
              padding: '3px 9px',
              borderRadius: 12,
              border: `1px solid ${status === s ? ESTIMATE_STATUS_COLORS[s] : borderColor}`,
              background: status === s ? `${ESTIMATE_STATUS_COLORS[s]}20` : 'transparent',
              color: status === s ? ESTIMATE_STATUS_COLORS[s] : textSecondary,
              fontSize: 11,
              fontWeight: status === s ? 700 : 500,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Line items table */}
      <div style={{ marginBottom: 8 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '3fr 1fr 1fr 1.5fr 1.5fr 28px',
          gap: 4,
          marginBottom: 4,
        }}>
          {['Description', 'Qty', 'Unit', 'Unit Price', 'Total', ''].map((label) => (
            <div key={label} style={{ fontSize: 10, fontWeight: 600, color: textSecondary, textTransform: 'uppercase', paddingLeft: 2 }}>
              {label}
            </div>
          ))}
        </div>
        {lineItems.map((item, i) => (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '3fr 1fr 1fr 1.5fr 1.5fr 28px',
              gap: 4,
              marginBottom: 4,
              alignItems: 'center',
            }}
          >
            <input
              value={item.description}
              onChange={(e) => updateItem(i, 'description', e.target.value)}
              placeholder="e.g. Remove old shingles"
              style={inputStyle}
            />
            <input
              type="number"
              min={0}
              value={item.quantity}
              onChange={(e) => updateItem(i, 'quantity', parseFloat(e.target.value) || 0)}
              style={inputStyle}
            />
            <input
              value={item.unit}
              onChange={(e) => updateItem(i, 'unit', e.target.value)}
              placeholder="sq"
              style={inputStyle}
            />
            <input
              type="number"
              min={0}
              step={0.01}
              value={item.unit_price}
              onChange={(e) => updateItem(i, 'unit_price', parseFloat(e.target.value) || 0)}
              style={inputStyle}
            />
            <div style={{ fontSize: 12, color: textPrimary, fontWeight: 500, paddingLeft: 2 }}>
              {formatCurrency(item.total)}
            </div>
            <button
              onClick={() => removeItem(i)}
              disabled={lineItems.length === 1}
              title="Remove line"
              style={{
                width: 24,
                height: 24,
                borderRadius: 4,
                border: `1px solid ${borderColor}`,
                background: 'transparent',
                color: textSecondary,
                fontSize: 13,
                cursor: lineItems.length === 1 ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 0,
                opacity: lineItems.length === 1 ? 0.4 : 1,
              }}
            >
              x
            </button>
          </div>
        ))}
        <button
          onClick={addItem}
          style={{
            marginTop: 4,
            padding: '4px 10px',
            borderRadius: 6,
            border: `1px solid ${borderColor}`,
            background: 'transparent',
            color: '#2563eb',
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + Add Line
        </button>
      </div>

      {/* Tax rate + totals */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: textSecondary, flexShrink: 0 }}>Tax Rate %</label>
        <input
          type="number"
          min={0}
          max={100}
          step={0.01}
          value={taxRateStr}
          onChange={(e) => setTaxRateStr(e.target.value)}
          style={{ ...inputStyle, width: 72 }}
        />
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontSize: 12, color: textSecondary }}>
            Subtotal: <span style={{ color: textPrimary, fontWeight: 500 }}>{formatCurrency(subtotal)}</span>
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: textPrimary }}>
            Total: {formatCurrency(total)}
          </div>
        </div>
      </div>

      {/* Notes */}
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        rows={2}
        style={{
          width: '100%',
          padding: '7px 10px',
          borderRadius: 6,
          border: `1px solid ${borderColor}`,
          background: inputBg,
          color: textPrimary,
          fontSize: 12,
          resize: 'vertical',
          boxSizing: 'border-box',
          marginBottom: 10,
          fontFamily: 'inherit',
        }}
      />

      {/* Save / Cancel */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handleSave}
          disabled={isSaving}
          style={{
            flex: 2,
            padding: '7px 0',
            borderRadius: 8,
            border: 'none',
            background: '#2563eb',
            color: '#ffffff',
            fontSize: 13,
            fontWeight: 700,
            cursor: isSaving ? 'wait' : 'pointer',
            opacity: isSaving ? 0.7 : 1,
          }}
        >
          {isSaving ? 'Saving...' : (initial ? 'Update Estimate' : 'Save Estimate')}
        </button>
        <button
          onClick={onCancel}
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
  )
}

// ===== Estimate Card (expanded detail) =====

interface EstimateCardProps {
  estimate: EstimateResponse
  isOwner: boolean
  onEdit: (e: EstimateResponse) => void
  onDelete: (id: string) => void
  isDeleting: boolean
}

function EstimateCard({ estimate, isOwner, onEdit, onDelete, isDeleting }: EstimateCardProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const [expanded, setExpanded] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'
  const statusColor = ESTIMATE_STATUS_COLORS[estimate.status] ?? '#64748b'

  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${borderColor}`,
      background: bgSecondary,
      marginBottom: 6,
      overflow: 'hidden',
    }}>
      {/* Summary row — click to expand */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 12px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        {/* Status badge */}
        <span style={{
          padding: '2px 8px',
          borderRadius: 10,
          background: `${statusColor}20`,
          color: statusColor,
          fontSize: 11,
          fontWeight: 700,
          textTransform: 'capitalize',
          flexShrink: 0,
        }}>
          {estimate.status}
        </span>
        <span style={{ fontSize: 12, color: textSecondary, flexShrink: 0 }}>
          {estimate.line_items.length} line{estimate.line_items.length !== 1 ? 's' : ''}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: textPrimary, flexShrink: 0 }}>
          {formatCurrency(estimate.total)}
        </span>
        <span style={{ fontSize: 11, color: textSecondary, flexShrink: 0 }}>
          {timeAgo(estimate.created_at)}
        </span>
        <span style={{ fontSize: 10, color: textSecondary }}>{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div style={{ padding: '0 12px 12px' }}>
          {/* Line items */}
          <div style={{
            borderRadius: 6,
            border: `1px solid ${borderColor}`,
            overflow: 'hidden',
            marginBottom: 8,
          }}>
            {/* Header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '3fr 1fr 1fr 1.5fr 1.5fr',
              gap: 4,
              padding: '6px 10px',
              background: darkMode ? '#0f172a' : '#f1f5f9',
              borderBottom: `1px solid ${borderColor}`,
            }}>
              {['Description', 'Qty', 'Unit', 'Unit Price', 'Total'].map((col) => (
                <div key={col} style={{ fontSize: 10, fontWeight: 600, color: textSecondary, textTransform: 'uppercase' }}>
                  {col}
                </div>
              ))}
            </div>
            {estimate.line_items.map((item, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '3fr 1fr 1fr 1.5fr 1.5fr',
                  gap: 4,
                  padding: '6px 10px',
                  borderBottom: i < estimate.line_items.length - 1 ? `1px solid ${borderColor}` : 'none',
                  background: i % 2 === 0 ? bgSecondary : (darkMode ? '#0f172a' : '#ffffff'),
                }}
              >
                <span style={{ fontSize: 12, color: textPrimary }}>{item.description}</span>
                <span style={{ fontSize: 12, color: textSecondary }}>{item.quantity}</span>
                <span style={{ fontSize: 12, color: textSecondary }}>{item.unit}</span>
                <span style={{ fontSize: 12, color: textSecondary }}>{formatCurrency(item.unit_price)}</span>
                <span style={{ fontSize: 12, color: textPrimary, fontWeight: 500 }}>{formatCurrency(item.total)}</span>
              </div>
            ))}
          </div>

          {/* Subtotal / Tax / Total */}
          <div style={{ textAlign: 'right', marginBottom: 8 }}>
            <div style={{ fontSize: 12, color: textSecondary }}>
              Subtotal: <span style={{ color: textPrimary }}>{formatCurrency(estimate.subtotal)}</span>
            </div>
            <div style={{ fontSize: 12, color: textSecondary }}>
              Tax ({(estimate.tax_rate * 100).toFixed(2)}%): <span style={{ color: textPrimary }}>{formatCurrency(estimate.total - estimate.subtotal)}</span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: textPrimary }}>
              Total: {formatCurrency(estimate.total)}
            </div>
          </div>

          {/* Notes */}
          {estimate.notes && (
            <div style={{
              fontSize: 12,
              color: textSecondary,
              padding: '6px 8px',
              borderRadius: 6,
              border: `1px solid ${borderColor}`,
              marginBottom: 8,
              lineHeight: '1.5',
            }}>
              {estimate.notes}
            </div>
          )}

          {/* Action buttons */}
          {isOwner && (
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={() => window.print()}
                title="Print / save as PDF"
                style={{
                  padding: '5px 10px',
                  borderRadius: 6,
                  border: `1px solid ${borderColor}`,
                  background: 'transparent',
                  color: textSecondary,
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                Print
              </button>
              <button
                onClick={() => onEdit(estimate)}
                style={{
                  padding: '5px 10px',
                  borderRadius: 6,
                  border: '1px solid #2563eb',
                  background: 'transparent',
                  color: '#2563eb',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Edit
              </button>
              {!confirmDelete ? (
                <button
                  onClick={() => setConfirmDelete(true)}
                  style={{
                    padding: '5px 10px',
                    borderRadius: 6,
                    border: '1px solid #ef4444',
                    background: 'transparent',
                    color: '#ef4444',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Delete
                </button>
              ) : (
                <div style={{ display: 'flex', gap: 4 }}>
                  <button
                    onClick={() => onDelete(estimate.id)}
                    disabled={isDeleting}
                    style={{
                      padding: '5px 10px',
                      borderRadius: 6,
                      border: 'none',
                      background: '#ef4444',
                      color: '#ffffff',
                      fontSize: 12,
                      fontWeight: 700,
                      cursor: isDeleting ? 'wait' : 'pointer',
                      opacity: isDeleting ? 0.7 : 1,
                    }}
                  >
                    {isDeleting ? 'Deleting...' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    style={{
                      padding: '5px 10px',
                      borderRadius: 6,
                      border: `1px solid ${borderColor}`,
                      background: 'transparent',
                      color: textSecondary,
                      fontSize: 12,
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ===== Estimates Section =====

interface EstimatesSectionProps {
  pinId: string
  isOwner: boolean
}

function EstimatesSection({ pinId, isOwner }: EstimatesSectionProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const { data: estimatesData, isLoading } = useEstimates(pinId)
  const deleteEstimate = useDeleteEstimate()
  const [showBuilder, setShowBuilder] = useState(false)
  const [editingEstimate, setEditingEstimate] = useState<EstimateResponse | null>(null)

  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'

  const estimates = estimatesData?.estimates ?? []

  function handleEdit(estimate: EstimateResponse) {
    setEditingEstimate(estimate)
    setShowBuilder(true)
  }

  function handleDelete(id: string) {
    deleteEstimate.mutate(id)
  }

  function handleBuilderDone() {
    setShowBuilder(false)
    setEditingEstimate(null)
  }

  return (
    <div style={{ marginTop: 12 }}>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: textSecondary, textTransform: 'uppercase' }}>
            Estimates
          </span>
          {estimates.length > 0 && (
            <span style={{
              padding: '1px 6px',
              borderRadius: 10,
              background: borderColor,
              color: textPrimary,
              fontSize: 11,
              fontWeight: 700,
            }}>
              {estimates.length}
            </span>
          )}
        </div>
        {isOwner && !showBuilder && (
          <button
            onClick={() => { setEditingEstimate(null); setShowBuilder(true) }}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              border: '1px solid #2563eb',
              background: 'transparent',
              color: '#2563eb',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            + New Estimate
          </button>
        )}
      </div>

      {/* Inline builder */}
      {showBuilder && (
        <EstimateBuilder
          pinId={pinId}
          initial={editingEstimate ?? undefined}
          onSaved={handleBuilderDone}
          onCancel={handleBuilderDone}
        />
      )}

      {/* List */}
      {isLoading && (
        <div style={{ fontSize: 12, color: textSecondary, padding: '8px 0' }}>
          Loading estimates...
        </div>
      )}
      {!isLoading && estimates.length === 0 && !showBuilder && (
        <div style={{ fontSize: 12, color: textSecondary, padding: '4px 0' }}>
          No estimates yet.
        </div>
      )}
      {!isLoading && estimates.length > 0 && (
        <div>
          {estimates.map((est) => (
            <EstimateCard
              key={est.id}
              estimate={est}
              isOwner={isOwner}
              onEdit={handleEdit}
              onDelete={handleDelete}
              isDeleting={deleteEstimate.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ===== Pin Detail View =====

interface PinDetailProps {
  pin: LeadPinResponse
  onBack: () => void
}

function PinDetail({ pin, onBack }: PinDetailProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const user = useAppStore((s) => s.user)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)
  const isTeamPin = pin.roofer_account_id !== user?.id
  const { data: activitiesData, isLoading: activitiesLoading } = useLeadPinActivities(pin.id)
  const { data: propertyData } = useProperty(pin.property_id)
  const updatePin = useUpdateLeadPin()
  const deletePin = useDeleteLeadPin()
  const createActivity = useCreatePinActivity()
  const [showUpdatePicker, setShowUpdatePicker] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showLogNote, setShowLogNote] = useState(false)
  const [noteText, setNoteText] = useState('')

  const handleUpdate = (disposition: LeadPinDisposition, notes: string, callbackDate?: string, contactName?: string, contactPhone?: string, contactEmail?: string) => {
    updatePin.mutate(
      { pinId: pin.id, data: { disposition, notes, callback_date: callbackDate, contact_name: contactName, contact_phone: contactPhone, contact_email: contactEmail } },
      {
        onSuccess: () => {
          setShowUpdatePicker(false)
        },
      },
    )
  }

  const handleDelete = () => {
    deletePin.mutate(pin.id, {
      onSuccess: () => {
        setSelectedLeadPinId(null)
      },
    })
  }

  const handleLogNote = () => {
    if (!noteText.trim()) return
    createActivity.mutate(
      { pinId: pin.id, data: { notes: noteText.trim() } },
      {
        onSuccess: () => {
          setNoteText('')
          setShowLogNote(false)
        },
      },
    )
  }

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'

  return (
    <div>
      {showUpdatePicker && (
        <DispositionPicker
          title="Update Disposition"
          initialDisposition={pin.disposition}
          initialNotes={pin.notes ?? ''}
          initialCallbackDate={pin.callback_date}
          initialContactName={pin.contact_name}
          initialContactPhone={pin.contact_phone}
          initialContactEmail={pin.contact_email}
          onConfirm={handleUpdate}
          onCancel={() => setShowUpdatePicker(false)}
          isLoading={updatePin.isPending}
        />
      )}

      <button
        onClick={onBack}
        style={{
          background: 'none',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontSize: 14,
          padding: 0,
          marginBottom: 12,
        }}
      >
        Back to list
      </button>

      {/* Pin header */}
      <div style={{
        background: bgSecondary,
        borderRadius: 10,
        padding: 12,
        marginBottom: 12,
        border: `1px solid ${borderColor}`,
      }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: textPrimary, marginBottom: 6 }}>
          {pin.address || 'Dropped pin'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <DispositionBadge disposition={pin.disposition} />
          <span style={{ fontSize: 12, color: textSecondary }}>
            {timeAgo(pin.created_at)}
          </span>
          {isTeamPin && pin.roofer_name && (
            <span style={{ fontSize: 12, color: textSecondary }}>
              by {pin.roofer_name}
            </span>
          )}
        </div>
        {pin.notes && (
          <div style={{
            marginTop: 8,
            fontSize: 13,
            color: textSecondary,
            lineHeight: '1.5',
            padding: '8px 10px',
            background: darkMode ? '#0f172a' : '#ffffff',
            borderRadius: 6,
            border: `1px solid ${borderColor}`,
          }}>
            {pin.notes}
          </div>
        )}
      </div>

      {/* Contact Info */}
      {(pin.contact_name || pin.contact_phone || pin.contact_email) && (
        <div style={{
          marginTop: 12,
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${borderColor}`,
          background: bgSecondary,
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: textSecondary, textTransform: 'uppercase', marginBottom: 8 }}>
            Contact Info
          </div>
          {pin.contact_name && (
            <div style={{ fontSize: 14, fontWeight: 600, color: textPrimary, marginBottom: 4 }}>
              {pin.contact_name}
            </div>
          )}
          {pin.contact_phone && (
            <div style={{ marginBottom: 4 }}>
              <a href={`tel:${pin.contact_phone}`} style={{ fontSize: 13, color: '#2563eb', textDecoration: 'none' }}>
                {pin.contact_phone}
              </a>
            </div>
          )}
          {pin.contact_email && (
            <div>
              <a href={`mailto:${pin.contact_email}`} style={{ fontSize: 13, color: '#2563eb', textDecoration: 'none' }}>
                {pin.contact_email}
              </a>
            </div>
          )}
        </div>
      )}

      {/* Property Info */}
      {propertyData && (
        <div style={{
          marginTop: 12,
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${borderColor}`,
          background: bgSecondary,
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: textSecondary, textTransform: 'uppercase', marginBottom: 8 }}>
            Property Info
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 13 }}>
            {propertyData.owner_name && (
              <>
                <span style={{ color: textSecondary }}>Owner</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>{propertyData.owner_name}</span>
              </>
            )}
            {propertyData.year_built && (
              <>
                <span style={{ color: textSecondary }}>Year Built</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>{propertyData.year_built}</span>
              </>
            )}
            {propertyData.estimated_roof_age != null && (
              <>
                <span style={{ color: textSecondary }}>Roof Age</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>{propertyData.estimated_roof_age} years</span>
              </>
            )}
            {propertyData.square_footage && (
              <>
                <span style={{ color: textSecondary }}>Sq Ft</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>{propertyData.square_footage.toLocaleString()}</span>
              </>
            )}
            {propertyData.assessed_value && (
              <>
                <span style={{ color: textSecondary }}>Assessed Value</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>${propertyData.assessed_value.toLocaleString()}</span>
              </>
            )}
            {propertyData.property_type && (
              <>
                <span style={{ color: textSecondary }}>Property Type</span>
                <span style={{ color: textPrimary, fontWeight: 500 }}>{propertyData.property_type}</span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Estimates */}
      <EstimatesSection pinId={pin.id} isOwner={!isTeamPin} />

      {/* Actions — hidden for team pins */}
      {!isTeamPin && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button
              onClick={() => setShowUpdatePicker(true)}
              style={{
                flex: 1,
                padding: '8px 0',
                borderRadius: 8,
                border: '1px solid #2563eb',
                background: 'transparent',
                color: '#2563eb',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Update
            </button>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                style={{
                  flex: 1,
                  padding: '8px 0',
                  borderRadius: 8,
                  border: '1px solid #ef4444',
                  background: 'transparent',
                  color: '#ef4444',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Delete
              </button>
            ) : (
              <button
                onClick={handleDelete}
                disabled={deletePin.isPending}
                style={{
                  flex: 1,
                  padding: '8px 0',
                  borderRadius: 8,
                  border: 'none',
                  background: '#ef4444',
                  color: '#ffffff',
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: deletePin.isPending ? 'wait' : 'pointer',
                  opacity: deletePin.isPending ? 0.7 : 1,
                }}
              >
                {deletePin.isPending ? 'Deleting...' : 'Confirm Delete'}
              </button>
            )}
          </div>
          {confirmDelete && (
            <button
              onClick={() => setConfirmDelete(false)}
              style={{
                width: '100%',
                padding: '6px 0',
                borderRadius: 8,
                border: `1px solid ${borderColor}`,
                background: 'transparent',
                color: textSecondary,
                fontSize: 12,
                cursor: 'pointer',
                marginBottom: 12,
              }}
            >
              Cancel delete
            </button>
          )}

          {/* Log Note */}
          {!showLogNote ? (
            <button
              onClick={() => setShowLogNote(true)}
              style={{
                width: '100%',
                padding: '8px 0',
                borderRadius: 8,
                border: '1px solid #16a34a',
                background: 'transparent',
                color: '#16a34a',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                marginBottom: 16,
              }}
            >
              Log Note
            </button>
          ) : (
            <div style={{ marginBottom: 16 }}>
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Add a note about this visit..."
                maxLength={1000}
                style={{
                  width: '100%',
                  minHeight: 72,
                  padding: 10,
                  borderRadius: 8,
                  border: `1px solid ${borderColor}`,
                  background: darkMode ? '#0f172a' : '#ffffff',
                  color: darkMode ? '#f1f5f9' : '#0f172a',
                  fontSize: 13,
                  lineHeight: '1.5',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                  marginBottom: 8,
                }}
                autoFocus
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={handleLogNote}
                  disabled={!noteText.trim() || createActivity.isPending}
                  style={{
                    flex: 1,
                    padding: '7px 0',
                    borderRadius: 8,
                    border: 'none',
                    background: '#16a34a',
                    color: '#ffffff',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: !noteText.trim() || createActivity.isPending ? 'not-allowed' : 'pointer',
                    opacity: !noteText.trim() || createActivity.isPending ? 0.5 : 1,
                  }}
                >
                  {createActivity.isPending ? 'Saving...' : 'Save Note'}
                </button>
                <button
                  onClick={() => { setShowLogNote(false); setNoteText('') }}
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

      {/* Photos */}
      <PhotoGallery pinId={pin.id} isOwner={!isTeamPin} />

      {/* Activity timeline */}
      <div style={{ fontSize: 13, fontWeight: 600, color: textSecondary, marginBottom: 8 }}>
        Activity History
      </div>
      {activitiesLoading && (
        <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 16 }}>
          Loading...
        </div>
      )}
      {activitiesData && activitiesData.activities.length === 0 && (
        <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 16 }}>
          No activity yet
        </div>
      )}
      {activitiesData && activitiesData.activities.length > 0 && (
        <div style={{
          maxHeight: 280,
          overflowY: 'auto',
          borderRadius: 8,
          border: `1px solid ${borderColor}`,
        }}>
          {activitiesData.activities.map((activity, i) => (
            <div
              key={activity.id}
              style={{
                padding: '10px 12px',
                borderBottom: i < activitiesData.activities.length - 1
                  ? `1px solid ${borderColor}`
                  : 'none',
                background: i % 2 === 0 ? bgSecondary : (darkMode ? '#0f172a' : '#ffffff'),
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <DispositionBadge disposition={activity.disposition} />
                <span style={{ fontSize: 11, color: textSecondary }}>
                  {timeAgo(activity.created_at)}
                </span>
              </div>
              {activity.notes && (
                <div style={{ fontSize: 12, color: textSecondary, lineHeight: '1.4', marginTop: 4 }}>
                  {activity.notes}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ===== Main LeadPinPanel =====

function LeadPinPanel() {
  const darkMode = useAppStore((s) => s.darkMode)
  const isPinDropMode = useAppStore((s) => s.isPinDropMode)
  const setIsPinDropMode = useAppStore((s) => s.setIsPinDropMode)
  const selectedLeadPinId = useAppStore((s) => s.selectedLeadPinId)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)

  const [expanded, setExpanded] = useState(true)
  const [exporting, setExporting] = useState(false)
  const { data: pinsData, isLoading: pinsLoading } = useLeadPins()

  // Direct fetch for the selected pin (used when pin isn't in the bbox list)
  const { data: pinDetail, error: pinDetailError } = useLeadPinDetail(selectedLeadPinId)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'
  const cardBg = darkMode ? '#0f172a' : '#ffffff'

  // Find selected pin: try list data first, fall back to direct fetch
  const selectedPin = selectedLeadPinId
    ? pinsData?.pins.find((p) => p.id === selectedLeadPinId) ?? pinDetail ?? null
    : null

  const pinCount = pinsData?.total ?? 0

  return (
    <div style={{ borderBottom: `1px solid ${borderColor}` }}>

      {/* Collapsible header */}
      {!selectedLeadPinId && (
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
          <span>Lead Pins{pinCount > 0 ? ` (${pinCount})` : ''}</span>
          <span style={{ fontSize: 11, color: textSecondary }}>
            {expanded ? '▲' : '▼'}
          </span>
        </button>
      )}

      {/* Pin list view — show when no pin is selected */}
      {!selectedLeadPinId && expanded && (
        <div style={{ padding: '0 16px 16px' }}>
          {/* Pin-drop toggle + Export CSV */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            marginBottom: 14,
          }}>
            <button
              onClick={async () => {
                setExporting(true)
                try {
                  await exportLeadsCsv()
                } catch {
                  // Silently handle — 401 already redirects to login
                } finally {
                  setExporting(false)
                }
              }}
              disabled={exporting}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: `1px solid ${borderColor}`,
                background: 'transparent',
                color: textSecondary,
                fontSize: 12,
                fontWeight: 600,
                cursor: exporting ? 'wait' : 'pointer',
                opacity: exporting ? 0.6 : 1,
              }}
            >
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
            <button
              onClick={() => setIsPinDropMode(!isPinDropMode)}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: isPinDropMode
                  ? '2px solid #8b5cf6'
                  : `1px solid ${borderColor}`,
                background: isPinDropMode ? '#8b5cf620' : 'transparent',
                color: isPinDropMode ? '#8b5cf6' : textSecondary,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                transition: 'all 0.12s',
              }}
            >
              <span style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: isPinDropMode ? '#8b5cf6' : textSecondary,
              }} />
              {isPinDropMode ? 'Drop mode ON' : 'Drop pin'}
            </button>
          </div>

          {isPinDropMode && (
            <div style={{
              fontSize: 12,
              color: '#8b5cf6',
              background: '#8b5cf610',
              border: '1px solid #8b5cf640',
              borderRadius: 8,
              padding: '8px 12px',
              marginBottom: 12,
              lineHeight: '1.5',
            }}>
              Tap anywhere on the map to drop a pin. Click an existing pin to view it.
            </div>
          )}

          {/* Pin list */}
          {pinsLoading && (
            <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 24 }}>
              Loading pins...
            </div>
          )}
          {!pinsLoading && pinsData && pinsData.pins.length === 0 && (
            <div style={{
              fontSize: 13,
              color: textSecondary,
              textAlign: 'center',
              padding: '24px 16px',
              lineHeight: '1.6',
            }}>
              No pins in this area yet.
              {!isPinDropMode && (
                <span> Tap "Drop pin" to start tracking leads.</span>
              )}
            </div>
          )}
          {!pinsLoading && pinsData && pinsData.pins.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: textSecondary, marginBottom: 8 }}>
                {pinsData.total} pin{pinsData.total !== 1 ? 's' : ''} in view
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pinsData.pins.map((pin) => (
                  <button
                    key={pin.id}
                    onClick={() => setSelectedLeadPinId(pin.id)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: cardBg,
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = bgSecondary
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = cardBg
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
                        marginBottom: 4,
                      }}>
                        {pin.address || 'Dropped pin'}
                      </div>
                      <DispositionBadge disposition={pin.disposition} />
                      {pin.roofer_name && (
                        <div style={{ fontSize: 11, color: textSecondary, marginTop: 1 }}>
                          by {pin.roofer_name}
                        </div>
                      )}
                    </div>
                    <span style={{ fontSize: 11, color: textSecondary, flexShrink: 0 }}>
                      {timeAgo(pin.created_at)}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Pin detail — always visible when selected, regardless of collapsed state */}
      {selectedLeadPinId && selectedPin && (
        <div style={{ padding: 16 }}>
          <PinDetail
            pin={selectedPin}
            onBack={() => setSelectedLeadPinId(null)}
          />
        </div>
      )}
      {selectedLeadPinId && !selectedPin && (
        <div style={{ padding: 16 }}>
          <button
            onClick={() => setSelectedLeadPinId(null)}
            style={{
              background: 'none',
              border: 'none',
              color: '#2563eb',
              cursor: 'pointer',
              fontSize: 14,
              padding: 0,
              marginBottom: 12,
            }}
          >
            Back to list
          </button>
          <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 24 }}>
            {pinDetailError
              ? `Failed to load pin: ${pinDetailError instanceof Error ? pinDetailError.message : 'Unknown error'}`
              : 'Loading pin...'}
          </div>
        </div>
      )}
    </div>
  )
}

export default LeadPinPanel
