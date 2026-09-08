import React, { useEffect, useMemo, useState } from 'react';
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


/* =========================================================
   API
========================================================= */

const API = import.meta.env.VITE_API_URL || '';


async function api(path, options = {}) {

  const response = await fetch(
    API + path,
    options
  );

  if (!response.ok) {

    let message = response.statusText;

    try {
      const body = await response.json();

      message =
        body.detail ||
        body.message ||
        JSON.stringify(body);
    } catch {
      try {
        message = await response.text();
      } catch {
        // Keep statusText.
      }
    }

    throw new Error(
      message || 'Request failed'
    );
  }

  return response.json();
}


/* =========================================================
   BADGE
========================================================= */

function Badge({
  children,
  type = ''
}) {

  return (
    <span
      className={
        'badge ' +
        String(type).toLowerCase()
      }
    >
      {children}
    </span>
  );
}


/* =========================================================
   APP
========================================================= */

function App() {

  const [docs, setDocs] = useState([]);
  const [facts, setFacts] = useState([]);
  const [rels, setRels] = useState([]);

  const [tab, setTab] = useState('Overview');

  const [q, setQ] = useState('');

  const [busy, setBusy] = useState(false);

  const [selected, setSelected] = useState(null);

  const [mobileMenuOpen, setMobileMenuOpen] =
    useState(false);


  const nav = [
    'Overview',
    'Documents',
    'Facts',
    'Relationships',
    'Evaluation'
  ];


  /* =======================================================
     LOAD DATA
  ======================================================= */

  const load = async () => {

    const [
      documents,
      allFacts,
      relationships
    ] = await Promise.all([

      api('/api/documents'),

      api('/api/facts'),

      api('/api/relationships')

    ]);

    setDocs(
      Array.isArray(documents)
        ? documents
        : []
    );

    setFacts(
      Array.isArray(allFacts)
        ? allFacts
        : []
    );

    setRels(
      Array.isArray(relationships)
        ? relationships
        : []
    );
  };


  useEffect(() => {

    load().catch((error) => {
      console.error(
        'Initial load failed:',
        error
      );
    });

  }, []);


  /* =======================================================
     TAB
  ======================================================= */

  const changeTab = (name) => {

    setTab(name);

    setMobileMenuOpen(false);

  };


  /* =======================================================
     UPLOAD
  ======================================================= */

  const upload = async (event) => {

    const selectedFiles =
      event.target.files;

    if (
      !selectedFiles ||
      selectedFiles.length === 0
    ) {
      return;
    }


    setBusy(true);


    const formData =
      new FormData();


    [...selectedFiles].forEach(
      (file) => {

        formData.append(
          'files',
          file
        );

      }
    );


    try {

      await api(
        '/api/documents',
        {
          method: 'POST',
          body: formData
        }
      );


      await load();


      setTab('Documents');

      setMobileMenuOpen(false);

    } catch (error) {

      console.error(error);

      alert(
        error.message ||
        'Failed to upload PDF.'
      );

    } finally {

      setBusy(false);

      // Allow same file to be selected again.
      event.target.value = '';

    }
  };


  /* =======================================================
     RESET
  ======================================================= */

  const reset = async () => {

    const confirmed =
      window.confirm(
        'Delete all local documents, facts and relationships?'
      );


    if (!confirmed) {
      return;
    }


    try {

      await api(
        '/api/reset',
        {
          method: 'DELETE'
        }
      );


      await load();


      setSelected(null);

      setMobileMenuOpen(false);

    } catch (error) {

      console.error(error);

      alert(
        error.message ||
        'Failed to reset data.'
      );

    }
  };


  /* =======================================================
     REFRESH
  ======================================================= */

  const refresh = async () => {

    try {

      await load();

    } catch (error) {

      console.error(
        'Refresh failed:',
        error
      );

      alert(
        error.message ||
        'Failed to refresh data.'
      );

    } finally {

      setMobileMenuOpen(false);

    }
  };


  /* =======================================================
     FACT FILTER
  ======================================================= */

  const filteredFacts = useMemo(() => {

    const search =
      q.trim().toLowerCase();


    if (!search) {
      return facts;
    }


    return facts.filter(
      (fact) => {

        const searchable = [

          fact.text,

          fact.filename,

          fact.evidence,

          fact.subject,

          fact.predicate,

          fact.value,

          fact.unit,

          fact.normalized_value,

          fact.normalized_unit,

          ...(Array.isArray(fact.entities)
            ? fact.entities
            : []),

          ...(Array.isArray(fact.dates)
            ? fact.dates
            : [])

        ]
          .filter(
            (value) =>
              value !== null &&
              value !== undefined
          )
          .join(' ')
          .toLowerCase();


        return searchable.includes(
          search
        );
      }
    );

  }, [facts, q]);


  return (

    <div className="app">


      {/* ===================================================
          DESKTOP SIDEBAR
      =================================================== */}

      <aside>

        <div className="brand">

          <div className="logo">
            FK
          </div>

          <div>
            <b>
              Fact Knowledge
            </b>

            <small>
              Layer
            </small>
          </div>

        </div>


        {nav.map((name) => (

          <button
            className={
              tab === name
                ? 'nav active'
                : 'nav'
            }
            onClick={() =>
              changeTab(name)
            }
            key={name}
          >

            {name === 'Overview' && (
              <Database />
            )}

            {name === 'Documents' && (
              <FileText />
            )}

            {name === 'Facts' && (
              <Search />
            )}

            {name === 'Relationships' && (
              <Network />
            )}

            {name === 'Evaluation' && (
              <CheckCircle2 />
            )}

            {name}

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


      {/* ===================================================
          MOBILE OVERLAY
      =================================================== */}

      {mobileMenuOpen && (

        <div
          className="mobile-overlay"
          onClick={() =>
            setMobileMenuOpen(false)
          }
        />

      )}


      {/* ===================================================
          MOBILE DRAWER
      =================================================== */}

      <div
        className={
          mobileMenuOpen
            ? 'mobile-drawer open'
            : 'mobile-drawer'
        }
      >

        <div className="mobile-drawer-header">

          <div className="brand">

            <div className="logo">
              FK
            </div>

            <div>
              <b>
                Fact Knowledge
              </b>

              <small>
                Layer
              </small>
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


        <div className="mobile-nav">

          {nav.map((name) => (

            <button
              className={
                tab === name
                  ? 'nav active'
                  : 'nav'
              }
              onClick={() =>
                changeTab(name)
              }
              key={name}
            >

              {name === 'Overview' && (
                <Database />
              )}

              {name === 'Documents' && (
                <FileText />
              )}

              {name === 'Facts' && (
                <Search />
              )}

              {name === 'Relationships' && (
                <Network />
              )}

              {name === 'Evaluation' && (
                <CheckCircle2 />
              )}

              {name}

            </button>

          ))}

        </div>


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


      {/* ===================================================
          MAIN
      =================================================== */}

      <main>


        {/* Mobile menu */}

        <button
          className="mobile-menu-button"
          onClick={() =>
            setMobileMenuOpen(true)
          }
          aria-label="Open menu"
        >

          <Menu size={21} />

          <span>
            Menu
          </span>

        </button>


        {/* =================================================
            HEADER
        ================================================= */}

        <header>

          <div>

            <h1>
              {tab}
            </h1>

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
              disabled={busy}
            />

          </label>

        </header>


        {/* =================================================
            OVERVIEW
        ================================================= */}

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

                <DocTable
                  docs={docs}
                />

              </section>


              <section className="panel">

                <h2>
                  Relationship summary
                </h2>


                {rels.length === 0 ? (

                  <div className="empty">

                    No relationships found yet.

                    <br />

                    Upload multiple related PDFs
                    to build cross-document
                    relationships.

                  </div>

                ) : (

                  rels
                    .slice(0, 5)
                    .map((relationship) => (

                      <Rel
                        key={relationship.id}
                        r={relationship}
                      />

                    ))

                )}

              </section>

            </div>

          </>

        )}


        {/* =================================================
            DOCUMENTS
        ================================================= */}

        {tab === 'Documents' && (

          <section className="panel">

            <h2>
              Documents
            </h2>

            <DocTable
              docs={docs}
            />

          </section>

        )}


        {/* =================================================
            FACTS
        ================================================= */}

        {tab === 'Facts' && (

          <section className="panel">

            <div className="toolbar">

              <h2>
                Facts
              </h2>


              <input
                placeholder="Search facts…"
                value={q}
                onChange={(event) =>
                  setQ(event.target.value)
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
                .map((fact) => (

                  <Fact
                    key={fact.id}
                    f={fact}
                    onClick={() =>
                      setSelected(fact)
                    }
                  />

                ))

            )}

          </section>

        )}


        {/* =================================================
            RELATIONSHIPS
        ================================================= */}

        {tab === 'Relationships' && (

          <section className="panel">

            <h2>
              Cross-document relationships
            </h2>


            {rels.length === 0 ? (

              <div className="empty">

                No relationships found.

                <br />

                Upload two or more related PDFs
                to compare facts.

              </div>

            ) : (

              rels.map((relationship) => (

                <Rel
                  key={relationship.id}
                  r={relationship}
                  detailed
                />

              ))

            )}

          </section>

        )}


        {/* =================================================
            EVALUATION
        ================================================= */}

        {tab === 'Evaluation' && (

          <Evaluation
            rels={rels}
            facts={facts}
          />

        )}


        {/* =================================================
            FACT INSPECTOR
        ================================================= */}

        {selected && (

          <div className="drawer">

            <button
              className="close"
              onClick={() =>
                setSelected(null)
              }
              aria-label="Close fact inspector"
            >
              ×
            </button>


            <h2>
              Fact Inspector
            </h2>


            <Badge
              type={selected.fact_type}
            >
              {selected.fact_type || 'fact'}
            </Badge>


            <h3>
              {selected.text}
            </h3>


            <p className="muted">

              {selected.filename}

              {' · '}

              page {selected.page}

            </p>


            {/* Structured information */}

            <div className="fact-details">

              <div>

                <span>
                  Subject
                </span>

                <strong>
                  {selected.subject || '—'}
                </strong>

              </div>


              <div>

                <span>
                  Predicate
                </span>

                <strong>
                  {selected.predicate || '—'}
                </strong>

              </div>


              <div>

                <span>
                  Value
                </span>

                <strong>

                  {selected.value !== null &&
                  selected.value !== undefined &&
                  selected.value !== ''
                    ? selected.value
                    : '—'}

                </strong>

              </div>


              <div>

                <span>
                  Unit
                </span>

                <strong>
                  {selected.unit || '—'}
                </strong>

              </div>

            </div>


            {/* Evidence */}

            <div className="evidence">

              <b>
                Source Evidence
              </b>

              <p>
                {selected.evidence ||
                  selected.text}
              </p>

            </div>


            {/* Metadata */}

            <div className="meta">

              <span>

                Confidence{' '}

                {typeof selected.confidence === 'number'
                  ? `${(
                      selected.confidence * 100
                    ).toFixed(0)}%`
                  : '—'}

              </span>


              <span>

                Normalized{' '}

                {selected.normalized_value !== null &&
                selected.normalized_value !== undefined &&
                selected.normalized_value !== ''
                  ? selected.normalized_value
                  : '—'}

                {' '}

                {selected.normalized_unit || ''}

              </span>

            </div>


            {/* Time */}

            {selected.dates &&
              selected.dates.length > 0 && (

                <div className="inspector-section">

                  <b>
                    Time / Date Context
                  </b>

                  <p>

                    {Array.isArray(
                      selected.dates
                    )
                      ? selected.dates.join(', ')
                      : selected.dates}

                  </p>

                </div>

              )}


            {/* Entities */}

            {selected.entities &&
              selected.entities.length > 0 && (

                <div className="inspector-section">

                  <b>
                    Entities
                  </b>

                  <p>

                    {Array.isArray(
                      selected.entities
                    )
                      ? selected.entities.join(', ')
                      : selected.entities}

                  </p>

                </div>

              )}


            {/* Warnings */}

            {selected.warnings &&
              selected.warnings.length > 0 && (

                <div className="warning">

                  <AlertTriangle />

                  <span>
                    {selected.warnings.join('; ')}
                  </span>

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

function Card({
  icon,
  n,
  t
}) {

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

function DocTable({
  docs
}) {

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
              Facts
            </span>

            <span>
              Status
            </span>

          </div>


          {docs.map((document) => (

            <div
              className="tr"
              key={document.id}
            >

              <span>

                <b>
                  {document.filename}
                </b>


                <small>

                  {document.sha256
                    ? document.sha256.slice(0, 12) + '…'
                    : ''}

                </small>

              </span>


              {/* =========================================
                  REAL PDF PAGE COUNT
              ========================================= */}

              <span>
                {Number.isFinite(
                  Number(document.page_count)
                )
                  ? Number(document.page_count)
                  : 0}
              </span>


              {/* =========================================
                  FACT COUNT
              ========================================= */}

              <span>
                {Number.isFinite(
                  Number(document.fact_count)
                )
                  ? Number(document.fact_count)
                  : 0}
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

          <br />

          Upload PDFs to begin.

        </div>

      )}

    </div>

  );
}


/* =========================================================
   FACT
========================================================= */

function Fact({
  f,
  onClick
}) {

  const hasValue =
    f.value !== null &&
    f.value !== undefined &&
    f.value !== '';


  const value = hasValue
    ? `${f.value}${f.unit ? ` ${f.unit}` : ''}`
    : null;


  return (

    <article
      className="fact"
      onClick={onClick}
    >

      <div>

        <Badge>
          {f.fact_type || 'fact'}
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

        {value ? (

          <>
            Value: {value}
            {' · '}
          </>

        ) : (

          <>
            Semantic fact
            {' · '}
          </>

        )}


        Confidence{' '}

        {typeof f.confidence === 'number'
          ? `${(
              f.confidence * 100
            ).toFixed(0)}%`
          : '—'}


        {' · '}


        {f.normalized_value !== null &&
        f.normalized_value !== undefined &&
        f.normalized_value !== ''
          ? `Normalized: ${f.normalized_value} ${
              f.normalized_unit || ''
            }`
          : 'not normalized'}

      </small>


      <ChevronRight />

    </article>

  );
}


/* =========================================================
   RELATIONSHIP
========================================================= */

function Rel({
  r,
  detailed = false
}) {

  return (

    <article className="rel">

      <div className="relhead">

        <Badge type={r.relation}>

          {r.relation ||
            'RELATED'}

        </Badge>


        <span>

          {typeof r.score === 'number'
            ? `${(
                r.score * 100
              ).toFixed(0)}% match`
            : '—'}

        </span>

      </div>


      <div className="pair">


        <div>

          <b>
            {r.document_a ||
              'Document A'}
          </b>


          <small>
            p.{r.page_a ?? '—'}
          </small>


          <p>
            {r.evidence_a ||
              r.fact_text_a ||
              'No evidence available.'}
          </p>

        </div>


        <div className="arrow">
          ↔
        </div>


        <div>

          <b>
            {r.document_b ||
              'Document B'}
          </b>


          <small>
            p.{r.page_b ?? '—'}
          </small>


          <p>
            {r.evidence_b ||
              r.fact_text_b ||
              'No evidence available.'}
          </p>

        </div>

      </div>


      {detailed && (

        <p className="explain">

          {r.explanation ||
            'No explanation available.'}

        </p>

      )}

    </article>

  );
}


/* =========================================================
   EVALUATION
========================================================= */

function Evaluation({
  rels,
  facts
}) {

  const counts = useMemo(() => {

    const result = {
      CORROBORATES: 0,
      CONTRADICTS: 0,
      RECONCILES: 0,
      RELATED: 0,
      UNCERTAIN: 0
    };


    rels.forEach(
      (relationship) => {

        const relation =
          String(
            relationship.relation || ''
          ).toUpperCase();


        if (
          Object.prototype.hasOwnProperty.call(
            result,
            relation
          )
        ) {

          result[relation] += 1;

        }

      }
    );


    return result;

  }, [rels]);


  return (

    <div className="grid">


      {/* =================================================
          REQUIRED BENCHMARK CASES
      ================================================= */}

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
            These represent different time scopes.
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
            and “promoted” facts must remain
            separate rather than assigning
            1,509 to the promotion statement.
          </p>

          <Badge type="related">
            HANDLED WITH WARNINGS
          </Badge>

        </div>

      </section>


      {/* =================================================
          OBSERVED RELATIONSHIPS
      ================================================= */}

      <section className="panel">

        <h2>
          Observed relationships
        </h2>


        {Object.entries(counts).map(
          ([name, count]) => (

            <div
              className="count"
              key={name}
            >

              <span>
                {name}
              </span>

              <strong>
                {count}
              </strong>

            </div>

          )
        )}


        <div className="count">

          <span>
            Total facts
          </span>

          <strong>
            {facts.length}
          </strong>

        </div>


        <div className="count">

          <span>
            Total relationships
          </span>

          <strong>
            {rels.length}
          </strong>

        </div>

      </section>

    </div>

  );
}


/* =========================================================
   ROOT
========================================================= */

createRoot(
  document.getElementById('root')
).render(
  <App />
);
