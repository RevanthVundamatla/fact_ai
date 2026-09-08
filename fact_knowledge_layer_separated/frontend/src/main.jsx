import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Upload,
  FileText,
  Network,
  Database,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Trash2,
  Search,
  ChevronRight,
  Menu,
  X
} from 'lucide-react';

import './styles.css';

const API = import.meta.env.VITE_API_URL || '';

const api = async (path, opt = {}) => {
  const r = await fetch(API + path, opt);

  if (!r.ok) {
    throw new Error((await r.text()) || r.statusText);
  }

  return r.json();
};

function Badge({ children, type = '' }) {
  return (
    <span className={'badge ' + type.toLowerCase()}>
      {children}
    </span>
  );
}

function App() {
  const [docs, setDocs] = useState([]);
  const [facts, setFacts] = useState([]);
  const [rels, setRels] = useState([]);

  const [tab, setTab] = useState('Overview');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);

  // Mobile menu state
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const nav = [
    'Overview',
    'Documents',
    'Facts',
    'Relationships',
    'Evaluation'
  ];

  const load = async () => {
    const [d, f, r] = await Promise.all([
      api('/api/documents'),
      api('/api/facts'),
      api('/api/relationships')
    ]);

    setDocs(d);
    setFacts(f);
    setRels(r);
  };

  useEffect(() => {
    load().catch(console.error);
  }, []);

  const changeTab = (name) => {
    setTab(name);
    setMobileMenuOpen(false);
  };

  const upload = async (e) => {
    if (!e.target.files?.length) return;

    setBusy(true);

    const fd = new FormData();

    [...e.target.files].forEach((f) => {
      fd.append('files', f);
    });

    try {
      await api('/api/documents', {
        method: 'POST',
        body: fd
      });

      await load();

      setTab('Documents');
      setMobileMenuOpen(false);
    } catch (x) {
      alert(x.message);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (
      confirm(
        'Delete all local documents, facts and relationships?'
      )
    ) {
      await api('/api/reset', {
        method: 'DELETE'
      });

      await load();
      setMobileMenuOpen(false);
    }
  };

  const refresh = async () => {
    try {
      await load();
    } catch (error) {
      console.error(error);
    }

    setMobileMenuOpen(false);
  };

  const filteredFacts = facts.filter((x) =>
    (
      x.text +
      x.filename +
      x.evidence
    )
      .toLowerCase()
      .includes(q.toLowerCase())
  );

  return (
    <div className="app">

      {/* =====================================================
          DESKTOP SIDEBAR
      ====================================================== */}

      <aside>
        <div className="brand">
          <div className="logo">FK</div>

          <div>
            <b>Fact Knowledge</b>
            <small>Layer</small>
          </div>
        </div>

        {nav.map((n) => (
          <button
            className={
              tab === n
                ? 'nav active'
                : 'nav'
            }
            onClick={() => changeTab(n)}
            key={n}
          >
            {n === 'Overview' ? (
              <Database />
            ) : n === 'Documents' ? (
              <FileText />
            ) : n === 'Facts' ? (
              <Search />
            ) : n === 'Relationships' ? (
              <Network />
            ) : (
              <CheckCircle2 />
            )}

            {n}
          </button>
        ))}

        <div className="sideBottom">

          <button
            className="nav"
            onClick={refresh}
          >
            <RefreshCw />
            Refresh
          </button>

          <button
            className="nav danger"
            onClick={reset}
          >
            <Trash2 />
            Reset data
          </button>

        </div>
      </aside>


      {/* =====================================================
          MOBILE OVERLAY
      ====================================================== */}

      {mobileMenuOpen && (
        <div
          className="mobile-overlay"
          onClick={() =>
            setMobileMenuOpen(false)
          }
        />
      )}


      {/* =====================================================
          MOBILE DRAWER
      ====================================================== */}

      <div
        className={
          mobileMenuOpen
            ? 'mobile-drawer open'
            : 'mobile-drawer'
        }
      >

        <div className="mobile-drawer-header">

          <div className="brand">
            <div className="logo">FK</div>

            <div>
              <b>Fact Knowledge</b>
              <small>Layer</small>
            </div>
          </div>

          <button
            className="mobile-close"
            onClick={() =>
              setMobileMenuOpen(false)
            }
            aria-label="Close menu"
          >
            <X size={22} />
          </button>

        </div>


        {/* Mobile navigation */}

        <div className="mobile-nav">

          {nav.map((n) => (
            <button
              className={
                tab === n
                  ? 'nav active'
                  : 'nav'
              }
              onClick={() => changeTab(n)}
              key={n}
            >
              {n === 'Overview' ? (
                <Database />
              ) : n === 'Documents' ? (
                <FileText />
              ) : n === 'Facts' ? (
                <Search />
              ) : n === 'Relationships' ? (
                <Network />
              ) : (
                <CheckCircle2 />
              )}

              {n}
            </button>
          ))}

        </div>


        {/* Mobile bottom actions */}

        <div className="sideBottom">

          <button
            className="nav"
            onClick={refresh}
          >
            <RefreshCw />
            Refresh
          </button>

          <button
            className="nav danger"
            onClick={reset}
          >
            <Trash2 />
            Reset data
          </button>

        </div>

      </div>


      {/* =====================================================
          MAIN CONTENT
      ====================================================== */}

      <main>

        {/* Mobile menu button */}

        <button
          className="mobile-menu-button"
          onClick={() =>
            setMobileMenuOpen(true)
          }
          aria-label="Open menu"
        >
          <Menu size={21} />
          <span>Menu</span>
        </button>


        {/* =================================================
            HEADER
        ================================================== */}

        <header>

          <div>
            <h1>{tab}</h1>

            <p>
              PDF-grounded fact extraction,
              evidence and cross-document reasoning.
            </p>
          </div>

          <label className="upload">

            <Upload />

            {busy
              ? 'Processing…'
              : 'Upload PDFs'}

            <input
              type="file"
              accept=".pdf"
              multiple
              onChange={upload}
            />

          </label>

        </header>


        {/* =================================================
            OVERVIEW
        ================================================== */}

        {tab === 'Overview' && (
          <>
            <div className="cards">

              <Card
                icon={<FileText />}
                n={docs.length}
                t="Documents"
              />

              <Card
                icon={<Search />}
                n={facts.length}
                t="Facts"
              />

              <Card
                icon={<Network />}
                n={rels.length}
                t="Relationships"
              />

              <Card
                icon={<CheckCircle2 />}
                n={4}
                t="Evaluation cases"
              />

            </div>


            <div className="grid">

              <section className="panel">

                <h2>
                  Recent documents
                </h2>

                <DocTable docs={docs} />

              </section>


              <section className="panel">

                <h2>
                  Relationship summary
                </h2>

                {rels.length === 0 ? (
                  <div className="empty">
                    No relationships found yet.
                    Upload multiple related PDFs
                    to build cross-document relationships.
                  </div>
                ) : (
                  rels
                    .slice(0, 5)
                    .map((r) => (
                      <Rel
                        key={r.id}
                        r={r}
                      />
                    ))
                )}

              </section>

            </div>
          </>
        )}


        {/* =================================================
            DOCUMENTS
        ================================================== */}

        {tab === 'Documents' && (
          <section className="panel">

            <h2>
              Documents
            </h2>

            <DocTable docs={docs} />

          </section>
        )}


        {/* =================================================
            FACTS
        ================================================== */}

        {tab === 'Facts' && (
          <section className="panel">

            <div className="toolbar">

              <h2>
                Facts
              </h2>

              <input
                placeholder="Search facts…"
                value={q}
                onChange={(e) =>
                  setQ(e.target.value)
                }
              />

            </div>


            {filteredFacts.length === 0 ? (
              <div className="empty">
                No facts found.
              </div>
            ) : (
              filteredFacts
                .slice(0, 100)
                .map((f) => (
                  <Fact
                    key={f.id}
                    f={f}
                    onClick={() =>
                      setSelected(f)
                    }
                  />
                ))
            )}

          </section>
        )}


        {/* =================================================
            RELATIONSHIPS
        ================================================== */}

        {tab === 'Relationships' && (
          <section className="panel">

            <h2>
              Cross-document relationships
            </h2>

            {rels.length === 0 ? (
              <div className="empty">
                No relationships found.
                Upload two or more related PDFs
                to compare facts.
              </div>
            ) : (
              rels.map((r) => (
                <Rel
                  key={r.id}
                  r={r}
                  detailed
                />
              ))
            )}

          </section>
        )}


        {/* =================================================
            EVALUATION
        ================================================== */}

        {tab === 'Evaluation' && (
          <Evaluation
            rels={rels}
          />
        )}


        {/* =================================================
            FACT INSPECTOR DRAWER
        ================================================== */}

        {selected && (
          <div className="drawer">

            <button
              className="close"
              onClick={() =>
                setSelected(null)
              }
            >
              ×
            </button>

            <h2>
              Fact Inspector
            </h2>

            <Badge
              type={selected.fact_type}
            >
              {selected.fact_type}
            </Badge>

            <h3>
              {selected.text}
            </h3>

            <p className="muted">
              {selected.filename}
              {' · '}
              page {selected.page}
            </p>

            <div className="evidence">

              <b>
                Evidence
              </b>

              <p>
                {selected.evidence}
              </p>

            </div>

            <div className="meta">

              <span>
                Confidence{' '}
                {(selected.confidence * 100).toFixed(0)}%
              </span>

              <span>
                Normalized{' '}
                {selected.normalized_value || '—'}
                {' '}
                {selected.normalized_unit || ''}
              </span>

            </div>

            {selected.warnings?.length > 0 && (
              <div className="warning">

                <AlertTriangle />

                {selected.warnings.join('; ')}

              </div>
            )}

          </div>
        )}

      </main>

    </div>
  );
}


/* =========================================================
   CARD
========================================================= */

function Card({ icon, n, t }) {

  return (
    <div className="card">

      <div className="icon">
        {icon}
      </div>

      <div>

        <strong>
          {n}
        </strong>

        <span>
          {t}
        </span>

      </div>

    </div>
  );
}


/* =========================================================
   DOCUMENT TABLE
========================================================= */

function DocTable({ docs }) {

  return (
    <div className="table">

      {docs.length ? (
        <>

          <div className="tr th">

            <span>
              Document
            </span>

            <span>
              Pages
            </span>

            <span>
              Status
            </span>

          </div>


          {docs.map((d) => (

            <div
              className="tr"
              key={d.id}
            >

              <span>

                <b>
                  {d.filename}
                </b>

                <small>
                  {d.sha256
                    ? d.sha256.slice(0, 12) + '…'
                    : ''}
                </small>

              </span>


              <span>
                {d.pages}
              </span>


              <span>

                <Badge type="ready">
                  Ready
                </Badge>

              </span>

            </div>

          ))}

        </>
      ) : (

        <div className="empty">
          No documents yet.
          Upload the starter PDFs to begin.
        </div>

      )}

    </div>
  );
}


/* =========================================================
   FACT
========================================================= */

function Fact({ f, onClick }) {

  return (
    <article
      className="fact"
      onClick={onClick}
    >

      <div>

        <Badge>
          {f.fact_type}
        </Badge>

        <span className="muted">
          {f.filename}
          {' · '}
          p.{f.page}
        </span>

      </div>


      <b>
        {f.text}
      </b>


      <p>
        {f.evidence}
      </p>


      <small>
        Confidence{' '}
        {(f.confidence * 100).toFixed(0)}%
        {' · '}
        {f.normalized_value || 'not normalized'}
        {' '}
        {f.normalized_unit || ''}
      </small>


      <ChevronRight />

    </article>
  );
}


/* =========================================================
   RELATIONSHIP
========================================================= */

function Rel({ r, detailed }) {

  return (
    <article className="rel">

      <div className="relhead">

        <Badge type={r.relation}>
          {r.relation}
        </Badge>

        <span>
          {(r.score * 100).toFixed(0)}% match
        </span>

      </div>


      <div className="pair">

        <div>

          <b>
            {r.document_a}
          </b>

          <small>
            p.{r.page_a}
          </small>

          <p>
            {r.evidence_a}
          </p>

        </div>


        <div className="arrow">
          ↔
        </div>


        <div>

          <b>
            {r.document_b}
          </b>

          <small>
            p.{r.page_b}
          </small>

          <p>
            {r.evidence_b}
          </p>

        </div>

      </div>


      {detailed && (
        <p className="explain">
          {r.explanation}
        </p>
      )}

    </article>
  );
}


/* =========================================================
   EVALUATION
========================================================= */

function Evaluation({ rels }) {

  const counts = Object.fromEntries(
    [
      'CORROBORATES',
      'CONTRADICTS',
      'RECONCILES',
      'RELATED',
      'UNCERTAIN'
    ].map((x) => [
      x,
      rels.filter(
        (r) => r.relation === x
      ).length
    ])
  );


  return (
    <div className="grid">

      <section className="panel">

        <h2>
          Required benchmark cases
        </h2>


        <div className="eval">

          <b>
            1 · Corroborated fact
          </b>

          <p>
            Delhivery FY24 revenue:
            ₹81,415m ↔ ₹8,142cr.
          </p>

          <Badge type="corroborates">
            CORROBORATES
          </Badge>

        </div>


        <div className="eval">

          <b>
            2 · Genuine / likely contradiction
          </b>

          <p>
            India FY25 GDP:
            6.4% ↔ 6.5%.
          </p>

          <Badge type="contradicts">
            LIKELY CONTRADICTION
          </Badge>

        </div>


        <div className="eval">

          <b>
            3 · Apparent contradiction
            explained by scope
          </b>

          <p>
            Q1/Q2/H1 GDP vs full FY25 GDP.
          </p>

          <Badge type="reconciles">
            RECONCILES
          </Badge>

        </div>


        <div className="eval">

          <b>
            4 · Extraction / reasoning failure
          </b>

          <p>
            Nearby “internal mobility”
            and “promoted” facts must
            remain separate.
          </p>

          <Badge type="related">
            HANDLED WITH WARNINGS
          </Badge>

        </div>

      </section>


      <section className="panel">

        <h2>
          Observed relationships
        </h2>


        {Object.entries(counts).map(
          ([k, v]) => (

            <div
              className="count"
              key={k}
            >

              <span>
                {k}
              </span>

              <strong>
                {v}
              </strong>

            </div>

          )
        )}

      </section>

    </div>
  );
}


createRoot(
  document.getElementById('root')
).render(
  <App />
);
