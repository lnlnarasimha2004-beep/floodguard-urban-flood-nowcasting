import heroImage from './assets/floodguard-hero-monsoon.png'

const proofPoints = [
  { number: '01', title: 'Rainfall → runoff', detail: 'Physics-informed simulation' },
  { number: '02', title: 'Drainage surcharge', detail: 'Network pressure detection' },
  { number: '03', title: 'Flood-safe routing', detail: 'Risk-aware response guidance' },
]

function LandingPage({ onEnter }) {
  return (
    <main className="landing-hero" style={{ backgroundImage: `url(${heroImage})` }}>
      <div className="hero-overlay" />
      <div className="hero-grain" />
      <section className="hero-content">
        <div className="hero-plate"><span className="hero-status-dot" /> NATIONAL HACKATHON PROTOTYPE <span className="plate-separator" /> DISASTER MANAGEMENT</div>
        <p className="hero-eyebrow">URBAN FLOOD INTELLIGENCE</p>
        <h1>FLOOD<span>GUARD</span></h1>
        <p className="hero-tagline">Know where the water will be before it gets there.</p>
        <p className="hero-value">AI + physics-powered urban flood nowcasting and flood-safe routing — 0–3 hours ahead.</p>
        <div className="hero-proof-points">
          {proofPoints.map((point) => <div className="proof-point" key={point.number}>
            <span className="proof-number">{point.number}</span><div><strong>{point.title}</strong><small>{point.detail}</small></div>
          </div>)}
        </div>
        <button className="hero-launch" onClick={onEnter}>Launch Dashboard <span>→</span></button>
        <div className="hero-footer"><span>STUDY AREA: BELLANDUR, BENGALURU</span><i /><span>PROTOTYPE / SIMULATED DATA</span></div>
      </section>
      <aside className="hero-corner-note"><span>FORECAST WINDOW</span><strong>H+0 — H+3</strong><small>Rainfall · terrain · drainage · ML</small></aside>
    </main>
  )
}

export default LandingPage
