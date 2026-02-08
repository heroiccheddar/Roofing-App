import FeedbackForm from '../components/FeedbackForm'

function FeedbackHistory() {
  // TODO: Implement in WP 4.3
  // - List of roofer's past canvassing sessions
  // - Form to submit new feedback
  // - Edit recent feedback (within 24h)
  // - Statistics on feedback accuracy
  // - Filter by date, zone, damage rate

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Canvassing Feedback</h1>
      <FeedbackForm />
      <div style={{ marginTop: '2rem' }}>
        <h2>Your Feedback History</h2>
        <p>Feedback history list will be implemented in WP 4.3</p>
      </div>
    </div>
  )
}

export default FeedbackHistory
