import React, {
  useCallback,
  useEffect,
  useMemo,
  useState
} from 'react';

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
  X,
  Play,
  Clock,
  Info
} from 'lucide-react';

import './styles.css';


/* =========================================================
   API
========================================================= */

const API = (
  import.meta.env.VITE_API_URL || ''
).replace(/\/$/, '');


async function api(path, options = {}) {

  const response = await fetch(
    `${API}${path}`,
    options
  );

  if (!response.ok) {

    let message =
      response.statusText ||
      'Request failed';

    try {

      const body =
        await response.json();

      message =
        body.detail ||
        body.message ||
        JSON.stringify(body);

    } catch {

      try {

        const text =
          await response.text();

        if (text) {
          message = text;
        }

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
   SAFE HELPERS
========================================================= */

function asArray(value) {

  if (Array.isArray(value)) {
    return value;
  }

  return [];
}


function asNumber(value) {

  const number =
    Number(value);

  return Number.isFinite(number)
    ? number
    : null;
}


function formatScore(value) {

  const number =
    asNumber(value);

  if (number === null) {
    return '—';
  }

  return `${(
    number * 100
  ).toFixed(0)}%`;
}


function normalizeText(value) {

  return String(
    value || ''
  )
    .toLowerCase()
    .replace(/[₹,%]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}


function relationName(value) {

  return String(
    value || ''
  ).trim().toUpperCase();
}


function safeJsonArray(value) {

  if (Array.isArray(value)) {
    return value;
  }

  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return [];
  }

  try {

    const parsed =
      JSON.parse(value);

    return Array.isArray(parsed)
      ? parsed
      : [];

  } catch {

    return [];
  }
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
        String(type)
          .toLowerCase()
          .replace(/\s+/g, '-')
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

  const [docs, setDocs] =
    useState([]);

  const [facts, setFacts] =
    useState([]);

  const [rels, setRels] =
    useState([]);

  const [tab, setTab] =
    useState('Overview');

  const [q, setQ] =
    useState('');

  const [busy, setBusy] =
    useState(false);

  const [analysisBusy, setAnalysisBusy] =
    useState(false);

  const [selected, setSelected] =
    useState(null);

  const [mobileMenuOpen, setMobileMenuOpen] =
    useState(false);

  const [loadError, setLoadError] =
    useState('');

  const [analysisMessage, setAnalysisMessage] =
    useState('');


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

  const load = useCallback(
    async () => {

      setLoadError('');

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

      return {
        documents,
        facts: allFacts,
        relationships
      };
    },
    []
  );


  useEffect(() => {

    load().catch((error) => {

      console.error(
        'Initial load failed:',
        error
      );

      setLoadError(
        error.message ||
        'Could not load application data.'
      );

    });

  }, [load]);


  /* =======================================================
     TAB
  ======================================================= */

  const changeTab = (name) => {

    setTab(name);

    setMobileMenuOpen(false);

  };


  /* =======================================================
     ANALYZE
  ======================================================= */

  const analyze = useCallback(
    async (showAlert = true) => {

      if (analysisBusy) {
        return;
      }

      setAnalysisBusy(true);

      setAnalysisMessage(
        'Analyzing cross-document relationships…'
      );

      try {

        const result =
          await api(
            '/api/analyze',
            {
              method: 'POST'
            }
          );

        await load();

        const created =
          Number(
            result.relationships_created || 0
          );

        setAnalysisMessage(
          created > 0
            ? `Analysis complete: ${created} relationship${created === 1 ? '' : 's'} found.`
            : 'Analysis complete. No cross-document relationships were found.'
        );

        if (showAlert && created === 0) {

          // Do not use an intrusive alert for the normal
          // zero-relationship case.
          console.info(
            'Analysis completed with no relationships.'
          );
        }

      } catch (error) {

        console.error(
          'Analysis failed:',
          error
        );

        setAnalysisMessage(
          error.message ||
          'Relationship analysis failed.'
        );

        if (showAlert) {

          alert(
            error.message ||
            'Relationship analysis failed.'
          );

        }

      } finally {

        setAnalysisBusy(false);

      }

    },
    [
      analysisBusy,
      load
    ]
  );


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

    setAnalysisMessage('');

    const formData =
      new FormData();

    [
      ...selectedFiles
    ].forEach((file) => {

      formData.append(
        'files',
        file
      );

    });

    try {

      /*
       * Step 1:
       * Upload + extract only.
       *
       * The backend intentionally does NOT run
       * relationship analysis during this request.
       */

      const uploadResult =
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

      /*
       * Step 2:
       * Start analysis separately.
       *
       * This preserves the fast upload endpoint while
       * still giving the user automatic relationship
       * analysis after ingestion.
       */

      if (
        uploadResult &&
        uploadResult.analysis_required
      ) {

        setBusy(false);

        await analyze(false);

      }

    } catch (error) {

      console.error(
        'Upload failed:',
        error
      );

      alert(
        error.message ||
        'Failed to upload PDF.'
      );

    } finally {

      setBusy(false);

      // Allow the same file to be selected again.
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

      setBusy(true);

      await api(
        '/api/reset',
        {
          method: 'DELETE'
        }
      );

      await load();

      setSelected(null);

      setAnalysisMessage('');

      setMobileMenuOpen(false);

      setTab('Overview');

    } catch (error) {

      console.error(
        'Reset failed:',
        error
      );

      alert(
        error.message ||
        'Failed to reset data.'
      );

    } finally {

      setBusy(false);

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

          ...asArray(fact.entities),

          ...asArray(fact.dates)

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


  /* =======================================================
     DERIVED COUNTS
  ======================================================= */

  const relationCounts =
    useMemo(() => {

      const result = {
        CORROBORATES: 0,
        CONTRADICTS: 0,
        RECONCILES: 0,
        RELATED: 0,
        UNCERTAIN: 0
      };

      rels.forEach(
        (relationship) => {

          const name =
            relationName(
              relationship.relation
            );

          if (
            Object.prototype.hasOwnProperty.call(
              result,
              name
            )
          ) {
            result[name] += 1;
          }

        }
      );

      return result;

    }, [rels]);


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
            disabled={busy || analysisBusy}
          >
            <RefreshCw
              className={
                analysisBusy
                  ? 'spin'
                  : ''
              }
            />

            Refresh
          </button>


          <button
            className="nav danger"
            onClick={reset}
            disabled={busy || analysisBusy}
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


          <div className="header-actions">

            <button
              className="analyze-button"
              onClick={() => analyze(true)}
              disabled={
                analysisBusy ||
                facts.length < 2
              }
              title={
                facts.length < 2
                  ? 'Upload at least two facts first'
                  : 'Run cross-document relationship analysis'
              }
            >

              {analysisBusy ? (
                <RefreshCw className="spin" />
              ) : (
                <Play />
              )}

              {analysisBusy
                ? 'Analyzing…'
                : 'Analyze'}

            </button>


            <label
              className={
                busy
                  ? 'upload disabled'
                  : 'upload'
              }
            >

              <Upload />

              {busy
                ? 'Uploading…'
                : 'Upload PDFs'}


              <input
                type="file"
                accept=".pdf,application/pdf"
                multiple
                onChange={upload}
                disabled={
                  busy ||
                  analysisBusy
                }
              />

            </label>

          </div>

        </header>


        {/* =================================================
            GLOBAL STATUS
        ================================================= */}

        {loadError && (

          <div className="warning">

            <AlertTriangle />

            <span>
              {loadError}
            </span>

          </div>

        )}


        {analysisMessage && (

          <div className="analysis-status">

            {analysisBusy ? (
              <RefreshCw className="spin" />
            ) : (
              <CheckCircle2 />
            )}

            <span>
              {analysisMessage}
            </span>

          </div>

        )}


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

                <div className="section-heading">

                  <div>

                    <h2>
                      Relationship summary
                    </h2>

                    <small className="muted">
                      Cross-document reasoning results
                    </small>

                  </div>


                  <button
                    className="small-button"
                    onClick={() => analyze(true)}
                    disabled={
                      analysisBusy ||
                      facts.length < 2
                    }
                  >

                    <Play size={15} />

                    Analyze

                  </button>

                </div>


                {rels.length === 0 ? (

                  <div className="empty">

                    <Network />

                    <span>
                      No relationships found yet.
                    </span>

                    <small>
                      Upload multiple related PDFs,
                      then run analysis.
                    </small>

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

            <div className="section-heading">

              <div>

                <h2>
                  Documents
                </h2>

                <small className="muted">
                  {docs.length} document
                  {docs.length === 1 ? '' : 's'} ingested
                </small>

              </div>

            </div>


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

              <div>

                <h2>
                  Facts
                </h2>

                <small className="muted">
                  {filteredFacts.length}
                  {' '}
                  matching fact
                  {filteredFacts.length === 1 ? '' : 's'}
                </small>

              </div>


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

                <Search />

                <span>
                  No facts found.
                </span>

                <small>
                  Upload a PDF or change the search.
                </small>

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

            <div className="section-heading">

              <div>

                <h2>
                  Cross-document relationships
                </h2>

                <small className="muted">
                  {rels.length}
                  {' '}
                  relationship
                  {rels.length === 1 ? '' : 's'}
                </small>

              </div>


              <button
                className="small-button"
                onClick={() => analyze(true)}
                disabled={
                  analysisBusy ||
                  facts.length < 2
                }
              >

                {analysisBusy ? (
                  <RefreshCw
                    size={15}
                    className="spin"
                  />
                ) : (
                  <Play size={15} />
                )}

                {analysisBusy
                  ? 'Analyzing…'
                  : 'Re-analyze'}

              </button>

            </div>


            {rels.length === 0 ? (

              <div className="empty">

                <Network />

                <span>
                  No relationships found.
                </span>

                <small>
                  Upload two or more related PDFs
                  and run analysis.
                </small>

                {facts.length < 2 && (
                  <small>
                    At least two extracted facts
                    are required.
                  </small>
                )}

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
                  selected.text ||
                  'No source evidence available.'}
              </p>

            </div>


            {/* Metadata */}

            <div className="meta">

              <span>

                Confidence{' '}

                {asNumber(selected.confidence) !== null
                  ? `${(
                      Number(
                        selected.confidence
                      ) * 100
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

            {asArray(selected.dates).length > 0 && (

              <div className="inspector-section">

                <b>
                  Time / Date Context
                </b>

                <p>

                  {asArray(
                    selected.dates
                  ).join(', ')}

                </p>

              </div>

            )}


            {/* Entities */}

            {asArray(selected.entities).length > 0 && (

              <div className="inspector-section">

                <b>
                  Entities
                </b>

                <p>

                  {asArray(
                    selected.entities
                  ).join(', ')}

                </p>

              </div>

            )}


            {/* Warnings */}

            {asArray(selected.warnings).length > 0 && (

              <div className="warning">

                <AlertTriangle />

                <span>
                  {asArray(
                    selected.warnings
                  ).join('; ')}
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


          {docs.map((document) => {

            const pages =
              asNumber(
                document.page_count
              );

            const factCount =
              asNumber(
                document.fact_count
              );

            return (

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
                      ? document.sha256.slice(
                          0,
                          12
                        ) + '…'
                      : ''}

                  </small>

                </span>


                {/* REAL PDF PAGE COUNT */}

                <span>
                  {pages !== null
                    ? pages
                    : '—'}
                </span>


                {/* FACT COUNT */}

                <span>
                  {factCount !== null
                    ? factCount
                    : '—'}
                </span>


                <span>

                  <Badge type="ready">
                    Ready
                  </Badge>

                </span>

              </div>

            );

          })}

        </>

      ) : (

        <div className="empty">

          <FileText />

          <span>
            No documents yet.
          </span>

          <small>
            Upload PDFs to begin.
          </small>

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
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {

        if (
          event.key === 'Enter' ||
          event.key === ' '
        ) {

          event.preventDefault();

          onClick();

        }

      }}
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
        {f.evidence ||
          f.text ||
          'No evidence available.'}
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

        {asNumber(f.confidence) !== null
          ? `${(
              Number(
                f.confidence
              ) * 100
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

  const relation =
    relationName(
      r.relation
    ) || 'RELATED';


  const signals =
    r.signals && typeof r.signals === 'object'
      ? r.signals
      : {};


  const signalEntries =
    Object.entries(
      signals
    );


  return (

    <article className="rel">

      <div className="relhead">

        <Badge type={relation}>

          {relation}

        </Badge>


        <span>

          {formatScore(r.score)}
          {' '}match

        </span>

      </div>


      <div className="pair">


        {/* =================================================
            FACT A
        ================================================= */}

        <div className="relation-fact">

          <div className="relation-source">

            <b>
              {r.document_a ||
                'Document A'}
            </b>

            <small>
              page {r.page_a ?? '—'}
            </small>

          </div>


          <div className="relation-label">
            Fact A
          </div>


          <p className="relation-fact-text">

            {r.fact_text_a ||
              r.evidence_a ||
              'No fact text available.'}

          </p>


          <div className="evidence">

            <b>
              Source Evidence
            </b>

            <p>
              {r.evidence_a ||
                r.fact_text_a ||
                'No evidence available.'}
            </p>

          </div>


          {(r.value_a !== null &&
            r.value_a !== undefined) && (

            <small className="relation-value">

              Value:{' '}

              {r.value_a}

              {' '}

              {r.unit_a || ''}

            </small>

          )}

        </div>


        <div className="arrow">
          ↔
        </div>


        {/* =================================================
            FACT B
        ================================================= */}

        <div className="relation-fact">

          <div className="relation-source">

            <b>
              {r.document_b ||
                'Document B'}
            </b>

            <small>
              page {r.page_b ?? '—'}
            </small>

          </div>


          <div className="relation-label">
            Fact B
          </div>


          <p className="relation-fact-text">

            {r.fact_text_b ||
              r.evidence_b ||
              'No fact text available.'}

          </p>


          <div className="evidence">

            <b>
              Source Evidence
            </b>

            <p>
              {r.evidence_b ||
                r.fact_text_b ||
                'No evidence available.'}
            </p>

          </div>


          {(r.value_b !== null &&
            r.value_b !== undefined) && (

            <small className="relation-value">

              Value:{' '}

              {r.value_b}

              {' '}

              {r.unit_b || ''}

            </small>

          )}

        </div>

      </div>


      {/* =================================================
          REASONING
      ================================================= */}

      {detailed && (

        <div className="relationship-reasoning">

          <div className="explain">

            <b>
              Reasoning
            </b>

            <p>
              {r.explanation ||
                'No explanation available.'}
            </p>

          </div>


          {signalEntries.length > 0 && (

            <div className="signals">

              <b>
                Reasoning signals
              </b>

              <div className="signal-list">

                {signalEntries.map(
                  ([name, value]) => (

                    <span
                      className="signal"
                      key={name}
                    >

                      <strong>
                        {name}
                      </strong>

                      <span>
                        {formatSignalValue(value)}
                      </span>

                    </span>

                  )
                )}

              </div>

            </div>

          )}

        </div>

      )}

    </article>

  );
}


/* =========================================================
   SIGNAL FORMATTER
========================================================= */

function formatSignalValue(value) {

  if (
    typeof value === 'boolean'
  ) {
    return value
      ? 'yes'
      : 'no';
  }

  if (
    typeof value === 'number'
  ) {

    if (
      value >= 0 &&
      value <= 1
    ) {

      return `${(
        value * 100
      ).toFixed(0)}%`;

    }

    return String(value);
  }

  if (
    Array.isArray(value)
  ) {
    return value.join(', ');
  }

  if (
    value === null ||
    value === undefined
  ) {
    return '—';
  }

  return String(value);
}


/* =========================================================
   EVALUATION
========================================================= */

function Evaluation({
  rels,
  facts
}) {

  /* =======================================================
     RELATION COUNTS
  ======================================================= */

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
          relationName(
            relationship.relation
          );

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


  /* =======================================================
     CASE 1
     Delhivery FY24 revenue
  ======================================================= */

  const case1 = useMemo(() => {

    const matching =
      rels.find(
        (r) => {

          const combined =
            normalizeText(
              [
                r.document_a,
                r.document_b,
                r.fact_text_a,
                r.fact_text_b,
                r.evidence_a,
                r.evidence_b,
                r.explanation
              ].join(' ')
            );

          const revenue =
            combined.includes(
              'revenue'
            );

          const delhivery =
            combined.includes(
              'delhivery'
            );

          const million =
            combined.includes(
              '81415'
            ) ||
            combined.includes(
              '81 415'
            );

          const crore =
            combined.includes(
              '8142'
            ) ||
            combined.includes(
              '8141.5'
            );

          return (
            revenue &&
            delhivery &&
            million &&
            crore
          );

        }
      );

    if (matching) {
      return {
        status:
          relationName(
            matching.relation
          ),
        relationship:
          matching
      };
    }

    /*
     * If the exact relationship is not found,
     * inspect the underlying facts so the UI can
     * distinguish "not found" from "wrong result".
     */

    const relevantFacts =
      facts.filter(
        (fact) => {

          const text =
            normalizeText(
              [
                fact.filename,
                fact.text,
                fact.evidence,
                fact.value,
                fact.unit
              ].join(' ')
            );

          return (
            text.includes('revenue') &&
            (
              text.includes('81415') ||
              text.includes('8142')
            )
          );

        }
      );

    return {
      status: 'NOT_DETECTED',
      relationship: null,
      facts: relevantFacts
    };

  }, [rels, facts]);


  /* =======================================================
     CASE 2
     India FY25 GDP 6.4 vs 6.5
  ======================================================= */

  const case2 = useMemo(() => {

    const matching =
      rels.find(
        (r) => {

          const combined =
            normalizeText(
              [
                r.document_a,
                r.document_b,
                r.fact_text_a,
                r.fact_text_b,
                r.evidence_a,
                r.evidence_b,
                r.explanation
              ].join(' ')
            );

          const gdp =
            combined.includes('gdp');

          const india =
            combined.includes('india');

          const fy25 =
            combined.includes('fy25') ||
            combined.includes('2024/25') ||
            combined.includes('2024 25');

          const values =
            (
              combined.includes('6.4') ||
              combined.includes('64')
            ) &&
            (
              combined.includes('6.5') ||
              combined.includes('65')
            );

          return (
            gdp &&
            india &&
            fy25 &&
            values
          );

        }
      );

    if (matching) {
      return {
        status:
          relationName(
            matching.relation
          ),
        relationship:
          matching
      };
    }

    return {
      status: 'NOT_DETECTED',
      relationship: null
    };

  }, [rels]);


  /* =======================================================
     CASE 3
     Q1/Q2/H1 vs FY25
  ======================================================= */

  const case3 = useMemo(() => {

    const matching =
      rels.find(
        (r) => {

          const combined =
            normalizeText(
              [
                r.document_a,
                r.document_b,
                r.fact_text_a,
                r.fact_text_b,
                r.evidence_a,
                r.evidence_b,
                r.explanation
              ].join(' ')
            );

          const gdp =
            combined.includes('gdp');

          const quarterOrHalf =
            combined.includes('q1') ||
            combined.includes('q2') ||
            combined.includes('first half') ||
            combined.includes('h1');

          const annual =
            combined.includes('fy25') ||
            combined.includes('2024/25') ||
            combined.includes('annual');

          return (
            gdp &&
            quarterOrHalf &&
            annual
          );

        }
      );

    if (matching) {
      return {
        status:
          relationName(
            matching.relation
          ),
        relationship:
          matching
      };
    }

    return {
      status: 'NOT_DETECTED',
      relationship: null
    };

  }, [rels]);


  /* =======================================================
     CASE 4
     Mobility vs promotion semantic separation
  ======================================================= */

  const case4 = useMemo(() => {

    const mobilityFacts =
      facts.filter(
        (fact) => {

          const text =
            normalizeText(
              [
                fact.text,
                fact.evidence,
                fact.predicate,
                fact.subject
              ].join(' ')
            );

          return (
            text.includes(
              'internal mobility'
            ) ||
            text.includes(
              'mobility'
            )
          );

        }
      );

    const promotionFacts =
      facts.filter(
        (fact) => {

          const text =
            normalizeText(
              [
                fact.text,
                fact.evidence,
                fact.predicate,
                fact.subject
              ].join(' ')
            );

          return (
            text.includes(
              'promoted'
            ) ||
            text.includes(
              'promotion'
            )
          );

        }
      );


    /*
     * Correct behavior:
     *
     * 1,509 employees moved through internal mobility.
     * 423 employees were promoted.
     *
     * These are different predicates/topics.
     * They must NOT be treated as a numerical contradiction.
     */

    const falseContradiction =
      rels.some(
        (r) => {

          const combined =
            normalizeText(
              [
                r.fact_text_a,
                r.fact_text_b,
                r.evidence_a,
                r.evidence_b
              ].join(' ')
            );

          const mobility =
            combined.includes(
              'mobility'
            );

          const promotion =
            combined.includes(
              'promoted'
            ) ||
            combined.includes(
              'promotion'
            );

          return (
            mobility &&
            promotion &&
            relationName(
              r.relation
            ) === 'CONTRADICTS'
          );

        }
      );


    return {
      mobilityFacts,
      promotionFacts,
      falseContradiction
    };

  }, [facts, rels]);


  return (

    <div className="evaluation-page">


      {/* =================================================
          EVALUATION HEADER
      ================================================= */}

      <section className="panel evaluation-intro">

        <div>

          <h2>
            Benchmark evaluation
          </h2>

          <p>
            The four required assignment cases are
            checked against the actual extracted facts
            and cross-document reasoning results.
          </p>

        </div>


        <div className="evaluation-status">

          <CheckCircle2 />

          <span>
            {facts.length > 0
              ? 'Live evaluation'
              : 'Waiting for documents'}
          </span>

        </div>

      </section>


      {/* =================================================
          CASE 1
      ================================================= */}

      <EvaluationCase
        number="1"
        title="Corroborated fact"
        description={
          'Delhivery FY24 revenue: ₹81,415 million ' +
          'in the annual report versus ₹8,142 crore ' +
          'in the earnings presentation.'
        }
        expected="CORROBORATES"
        result={case1.status}
        relationship={case1.relationship}
        success={
          case1.status === 'CORROBORATES'
        }
        sourceFacts={case1.facts}
      />


      {/* =================================================
          CASE 2
      ================================================= */}

      <EvaluationCase
        number="2"
        title="Genuine / likely contradiction"
        description={
          'India FY25 GDP growth is reported as ' +
          '6.4% in the Economic Survey and 6.5% ' +
          'in the IMF Article IV material.'
        }
        expected="CONTRADICTS"
        result={case2.status}
        relationship={case2.relationship}
        success={
          case2.status === 'CONTRADICTS'
        }
      />


      {/* =================================================
          CASE 3
      ================================================= */}

      <EvaluationCase
        number="3"
        title="Apparent contradiction explained by scope"
        description={
          'Q1/Q2/H1 GDP figures and the full FY25 ' +
          'GDP figure represent different time scopes, ' +
          'so they should be reconciled rather than ' +
          'treated as direct contradictions.'
        }
        expected="RECONCILES"
        result={case3.status}
        relationship={case3.relationship}
        success={
          case3.status === 'RECONCILES'
        }
      />


      {/* =================================================
          CASE 4
      ================================================= */}

      <section className="panel evaluation-case">

        <div className="eval-case-header">

          <div className="case-number">
            4
          </div>

          <div>

            <h3>
              Extraction / reasoning failure
            </h3>

            <p>
              The nearby “internal mobility” and
              “promoted” facts must remain separate.
              1,509 must not be attached to the
              promotion statement of 423 employees.
            </p>

          </div>

          <Badge
            type={
              case4.falseContradiction
                ? 'contradicts'
                : 'corroborates'
            }
          >
            {case4.falseContradiction
              ? 'FAILED'
              : 'HANDLED'}
          </Badge>

        </div>


        <div className="failure-grid">

          <div className="eval-evidence">

            <b>
              Internal mobility
            </b>

            {case4.mobilityFacts.length === 0 ? (

              <p className="muted">
                Source fact not detected.
              </p>

            ) : (

              case4.mobilityFacts
                .slice(0, 3)
                .map((fact) => (

                  <div
                    className="mini-evidence"
                    key={fact.id}
                  >

                    <span>
                      {fact.filename}
                      {' · '}
                      p.{fact.page}
                    </span>

                    <p>
                      {fact.evidence ||
                        fact.text}
                    </p>

                  </div>

                ))

            )}

          </div>


          <div className="eval-evidence">

            <b>
              Promotion
            </b>

            {case4.promotionFacts.length === 0 ? (

              <p className="muted">
                Source fact not detected.
              </p>

            ) : (

              case4.promotionFacts
                .slice(0, 3)
                .map((fact) => (

                  <div
                    className="mini-evidence"
                    key={fact.id}
                  >

                    <span>
                      {fact.filename}
                      {' · '}
                      p.{fact.page}
                    </span>

                    <p>
                      {fact.evidence ||
                        fact.text}
                    </p>

                  </div>

                ))

            )}

          </div>

        </div>


        <div className="eval-note">

          <Info />

          <span>

            Expected behavior: the two facts are
            semantically distinct and should not
            create a numerical contradiction.

          </span>

        </div>

      </section>


      {/* =================================================
          OBSERVED RELATIONSHIPS
      ================================================= */}

      <section className="panel">

        <div className="section-heading">

          <div>

            <h2>
              Observed relationships
            </h2>

            <small className="muted">
              Results from the actual reasoning engine
            </small>

          </div>

        </div>


        <div className="count-grid">

          {Object.entries(
            counts
          ).map(
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

        </div>

      </section>

    </div>

  );
}


/* =========================================================
   EVALUATION CASE COMPONENT
========================================================= */

function EvaluationCase({
  number,
  title,
  description,
  expected,
  result,
  success,
  relationship,
  sourceFacts = []
}) {

  const hasResult =
    Boolean(
      relationship
    );


  return (

    <section className="panel evaluation-case">

      <div className="eval-case-header">

        <div className="case-number">
          {number}
        </div>

        <div>

          <h3>
            {title}
          </h3>

          <p>
            {description}
          </p>

        </div>


        <Badge
          type={
            success
              ? expected
              : result === 'NOT_DETECTED'
                ? 'uncertain'
                : 'contradicts'
          }
        >

          {success
            ? 'PASS'
            : result === 'NOT_DETECTED'
              ? 'NOT DETECTED'
              : `FOUND: ${result}`}

        </Badge>

      </div>


      <div className="evaluation-result">

        <div>

          <span>
            Expected reasoning
          </span>

          <strong>
            {expected}
          </strong>

        </div>


        <div>

          <span>
            Actual reasoning
          </span>

          <strong>
            {result || '—'}
          </strong>

        </div>

      </div>


      {hasResult && (

        <div className="evaluation-evidence">

          <div className="eval-source">

            <b>
              Source A
            </b>

            <span>
              {relationship.document_a}
              {' · '}
              page {relationship.page_a}
            </span>

            <p>
              {relationship.evidence_a ||
                relationship.fact_text_a}
            </p>

          </div>


          <div className="eval-source">

            <b>
              Source B
            </b>

            <span>
              {relationship.document_b}
              {' · '}
              page {relationship.page_b}
            </span>

            <p>
              {relationship.evidence_b ||
                relationship.fact_text_b}
            </p>

          </div>

        </div>

      )}


      {hasResult && (

        <div className="eval-reasoning">

          <b>
            Reasoning
          </b>

          <p>
            {relationship.explanation ||
              'No explanation returned by the reasoning engine.'}
          </p>

        </div>

      )}


      {!hasResult &&
        sourceFacts.length > 0 && (

          <div className="evaluation-evidence">

            {sourceFacts
              .slice(0, 2)
              .map((fact) => (

                <div
                  className="eval-source"
                  key={fact.id}
                >

                  <b>
                    Detected source fact
                  </b>

                  <span>
                    {fact.filename}
                    {' · '}
                    page {fact.page}
                  </span>

                  <p>
                    {fact.evidence ||
                      fact.text}
                  </p>

                </div>

              ))}

          </div>

        )}


      {!hasResult &&
        sourceFacts.length === 0 && (

          <div className="eval-note">

            <Clock />

            <span>
              Run analysis after uploading the
              starter dataset to evaluate this case.
            </span>

          </div>

        )}

    </section>

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
