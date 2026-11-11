import { useEffect, useState } from 'react'



function App() {
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(null)
  const [file, setFile] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [analysisError, setAnalysisError] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState([])
  const [verification, setVerification] = useState(null)
  const [preparing, setPreparing] = useState(false)
  const [prepareError, setPrepareError] = useState(null)
  const [reserving, setReserving] = useState(false)
  const [reserveError, setReserveError] = useState(null)
  const [approval, setApproval] = useState(null)
  const [activeAnalysisTab, setActiveAnalysisTab] = useState('ready')



  useEffect(() => {
    async function loadHealth() {
      try {
        const response = await fetch('/api/health')
        if (!response.ok) throw new Error(`Backend svarede med status ${response.status}`)
        setHealth(await response.json())
      } catch (err) {
        setHealthError(err.message)
      }
    }
    loadHealth()
  }, [])



  async function analyzeFile() {
    if (!file) {
      setAnalysisError('Vælg først en Excel-fil.')
      return
    }
    setAnalyzing(true)
    setAnalysisError(null)
    setAnalysis(null)
    setVerification(null)
    setApproval(null)
    setSelectedKeys([])
    setActiveAnalysisTab('ready')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch('/api/analyze', { method: 'POST', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Filen kunne ikke analyseres.')
      setAnalysis(data)
      setActiveAnalysisTab(defaultAnalysisTab(data))
    } catch (err) {
      setAnalysisError(err.message)
    } finally {
      setAnalyzing(false)
    }
  }



  function productKey(product) {
    return product.ean || product.product_code
  }



  function toggleProduct(product) {
    const key = productKey(product)
    if (!key) return
    setSelectedKeys((current) =>
      current.includes(key)
        ? current.filter((value) => value !== key)
        : [...current, key]
    )
  }



  function selectAllReady() {
    setSelectedKeys(
      (analysis?.ready_products || [])
        .map(productKey)
        .filter(Boolean)
    )
  }



  async function prepareSelected() {
    if (!analysis?.analysis_id) {
      setPrepareError('Analysis ID mangler. Upload filen igen.')
      return
    }
    if (!selectedKeys.length) {
      setPrepareError('Vælg mindst ét produkt.')
      return
    }
    setPreparing(true)
    setPrepareError(null)
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysis.analysis_id)}/prepare`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_keys: selectedKeys }),
        }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Produkterne kunne ikke forberedes.')
      setAnalysis(data.analysis)
      setVerification(data.verification)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setPrepareError(err.message)
    } finally {
      setPreparing(false)
    }
  }

  async function reserveCodes(productKeys = selectedKeys) {
    if (!analysis?.analysis_id) {
      setReserveError('Analysis ID mangler. Upload filen igen.')
      return
    }
    if (!productKeys.length) {
      setReserveError('Vælg mindst ét produkt.')
      return
    }
    setReserving(true)
    setReserveError(null)
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysis.analysis_id)}/reserve-codes`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_keys: productKeys }),
        }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Sæther Code kunne ikke reserveres.')
      setAnalysis(data.analysis)
      if (data.blocked_count) {
        const messages = (data.reservations || []).flatMap((item) => item.errors || [])
        setReserveError(messages.join(' · ') || 'Mindst ét produkt blev blokeret.')
      }
      setSelectedKeys([])
    } catch (err) {
      setReserveError(err.message)
    } finally {
      setReserving(false)
    }
  }



  if (verification) {
    return (
      <main style={mainStyle}>
        <header style={headerStyle}>
          <h1 style={titleStyle}>Sæther Masterdata Automation</h1>
          <p style={subtitleStyle}>Verificering før godkendelse og M3</p>
        </header>
        <WorkflowProgress stage={approval ? 'download' : 'verification'} />
        <VerificationView
          verification={verification}
          approval={approval}
          onApproval={setApproval}
          onBack={() => {
            setVerification(null)
            setApproval(null)
          }}
        />
      </main>
    )
  }



  return (
    <main style={mainStyle}>
      <header style={headerStyle}>
        <h1 style={titleStyle}>Sæther Masterdata Automation</h1>
        <p style={subtitleStyle}>Analyse, klassifikation og oprettelse af nye produkter</p>
      </header>

      <WorkflowProgress stage="analysis" />



      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Systemstatus</h2>
        {!health && !healthError && <p>Forbinder til backend...</p>}
        {healthError && <ErrorBox>Backend fejl: {healthError}</ErrorBox>}
        {health && (
          <div style={gridStyle}>
            <StatusCard label="Backend" value={health.status === 'ok' ? 'Online' : 'Fejl'} color="#15803d" />
            <StatusCard
              label="Golden Record"
              value={health.golden_record_loaded ? 'Indlæst' : 'Ikke indlæst'}
              color={health.golden_record_loaded ? '#15803d' : '#b91c1c'}
            />
            <StatusCard label="Produkter" value={health.golden_record_products.toLocaleString('da-DK')} />
          </div>
        )}
      </section>



      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Importér produkter</h2>
        <p style={mutedStyle}>Vælg en Excel-fil fra leverandøren. Filen analyseres mod Golden Record, men der skrives ikke noget til M3.</p>
        <div style={uploadRowStyle}>
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null)
              setAnalysis(null)
              setAnalysisError(null)
              setVerification(null)
              setApproval(null)
              setSelectedKeys([])
              setActiveAnalysisTab('ready')
            }}
          />
          <button
            type="button"
            onClick={analyzeFile}
            disabled={analyzing}
            style={{ ...buttonStyle, background: analyzing ? '#9ca3af' : '#111827', cursor: analyzing ? 'wait' : 'pointer' }}
          >
            {analyzing ? 'Analyserer...' : 'Analyser'}
          </button>
        </div>
        {file && <p style={selectedFileStyle}>Valgt fil: <strong>{file.name}</strong></p>}
        {analysisError && <ErrorBox>{analysisError}</ErrorBox>}
      </section>



      {analysis && (
        <section style={sectionStyle}>
          <h2 style={sectionTitleStyle}>Analyse</h2>
          <p><strong>{analysis.source_file}</strong></p>
          <p style={mutedStyle}>Brand: <strong>{analysis.brand?.name || '-'}</strong>{' · '}{analysis.brand?.code || '-'}</p>
          <p style={mutedSmallStyle}>Generation-prefix: <strong>{analysis.brand?.generation_prefix || '-'}</strong>{' · '}{analysis.brand?.generation_prefix_status || '-'}</p>
          <div style={analysisGridStyle}>
            <StatusCard label="I alt" value={analysis.total} />
            <StatusCard label="Eksisterende" value={analysis.existing} color="#2563eb" />
            <StatusCard label="Klar" value={analysis.ready} color="#15803d" />
            <StatusCard label="Review" value={analysis.review} color="#d97706" />
            <StatusCard label="Kræver afklaring" value={analysis.ambiguous} color="#dc2626" />
          </div>
          <LifecycleSummary counts={analysis.lifecycle_counts || {}} />
          <div style={noticeStyle}>Analysen har ikke skrevet noget til M3.</div>

          <DownloadReadinessPanel stage="analysis" />



          <AnalysisTabs
            analysis={analysis}
            activeTab={activeAnalysisTab}
            onChange={setActiveAnalysisTab}
          />

          <div
            id={`analysis-panel-${activeAnalysisTab}`}
            role="tabpanel"
            aria-labelledby={`analysis-tab-${activeAnalysisTab}`}
          >
            {activeAnalysisTab === 'ready' && (
              <ReadySelectionSection
                products={analysis.ready_products || []}
                analysis={analysis}
                setAnalysis={setAnalysis}
                selectedKeys={selectedKeys}
                onToggle={toggleProduct}
                onSelectAll={selectAllReady}
                onClear={() => setSelectedKeys([])}
                onPrepare={prepareSelected}
                onReserve={() => reserveCodes(selectedKeys)}
                preparing={preparing}
                reserving={reserving}
                error={prepareError || reserveError}
              />
            )}

            {activeAnalysisTab === 'review' && (
              <ProductSection
                title={`Kræver review (${analysis.review})`}
                products={analysis.review_products || []}
                analysis={analysis}
                setAnalysis={setAnalysis}
                onPromoted={(key) => {
                  setSelectedKeys((current) => current.includes(key) ? current : [...current, key])
                  setActiveAnalysisTab('ready')
                }}
                onReserve={(key) => reserveCodes([key])}
                reserving={reserving}
                reserveError={reserveError}
              />
            )}

            {activeAnalysisTab === 'conflict' && (
              <ConflictSection
                products={analysis.conflict_products || []}
              />
            )}
          </div>
        </section>
      )}
    </main>
  )
}


function LifecycleSummary({ counts }) {
  const stages = [
    ['IDENTITY_REVIEW', 'Kodeklar / identitetsreview'],
    ['CODE_READY', 'Klar til Sæther Code'],
    ['MASTERDATA_REVIEW', 'MASTERDATA-review'],
    ['READY_FOR_APPROVAL', 'Klar til godkendelse'],
  ]
  return (
    <div style={lifecycleSummaryStyle}>
      <strong>MVP-flow</strong>
      <span>Analyse → Kodeklar/review → Sæther Code reserveret → MASTERDATA-review → Klar til godkendelse → Godkendt → Download</span>
      <div style={lifecycleCountsStyle}>
        {stages.map(([key, label]) => <span key={key}>{label}: <strong>{counts[key] || 0}</strong></span>)}
      </div>
    </div>
  )
}


function defaultAnalysisTab(analysis) {
  if ((analysis?.ready_products || []).length > 0) return 'ready'
  if ((analysis?.review_products || []).length > 0) return 'review'
  return 'conflict'
}


function AnalysisTabs({ analysis, activeTab, onChange }) {
  const tabs = [
    { key: 'ready', label: 'Klar', count: analysis.ready ?? (analysis.ready_products || []).length },
    { key: 'review', label: 'Kræver review', count: analysis.review ?? (analysis.review_products || []).length },
    { key: 'conflict', label: 'Kræver afklaring', count: analysis.ambiguous ?? (analysis.conflict_products || []).length },
  ]

  return (
    <div style={analysisTabsStyle} role="tablist" aria-label="Filtrér analyseresultat">
      {tabs.map((tab) => {
        const active = activeTab === tab.key
        const hasConflict = tab.key === 'conflict' && tab.count > 0
        return (
          <button
            key={tab.key}
            id={`analysis-tab-${tab.key}`}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={`analysis-panel-${tab.key}`}
            onClick={() => onChange(tab.key)}
            style={{
              ...analysisTabStyle,
              ...(hasConflict ? conflictAnalysisTabStyle : {}),
              ...(active ? activeAnalysisTabStyle : {}),
              ...(active && hasConflict ? activeConflictAnalysisTabStyle : {}),
            }}
          >
            {tab.label} ({tab.count})
          </button>
        )
      })}
    </div>
  )
}


function ReadySelectionSection({ products, analysis, setAnalysis, selectedKeys, onToggle, onSelectAll, onClear, onPrepare, onReserve, preparing, reserving, error }) {
  if (!products.length) return null
  const selectedProducts = products.filter((product) => selectedKeys.includes(product.ean || product.product_code))
  const needsReservation = selectedProducts.some((product) => !product.item_number)
  return (
    <div style={productSectionStyle}>
      <div style={sectionHeadingRowStyle}>
        <h3 style={productSectionTitleStyle}>Kodeklar / klar til godkendelse ({products.length})</h3>
        <div style={smallActionsStyle}>
          <button type="button" onClick={onSelectAll} style={secondaryButtonStyle}>Vælg alle</button>
          <button type="button" onClick={onClear} style={secondaryButtonStyle}>Fravælg alle</button>
        </div>
      </div>
      <div style={productListStyle}>
        {products.map((product) => {
          const key = product.ean || product.product_code
          const selected = selectedKeys.includes(key)
          return (
            <div key={key} style={{ ...productCardStyle, borderColor: selected ? '#2563eb' : '#e5e7eb' }}>
              <div style={selectHeaderStyle}>
                <label style={checkboxLabelStyle}>
                  <input type="checkbox" checked={selected} onChange={() => onToggle(product)} />
                  <span>Vælg produkt</span>
                </label>
                <StatusBadge label="KLAR" tone="green" />
              </div>
              <ProductHeader product={product} />
              <ReadyFields product={product} />
               <LifecycleNextStep product={product} />
              <details style={detailsStyle}>
                <summary style={detailsSummaryStyle}>Vis afledte MASTERDATA-værdier og evidens</summary>
                <MasterDataEvidence masterdata={product.masterdata || {}} />
              </details>
              <MasterDataReviewEditor
                product={product}
                analysis={analysis}
                setAnalysis={setAnalysis}
              />
            </div>
          )
        })}
      </div>
      <div style={selectionFooterStyle}>
        <div>
          <strong>{selectedKeys.length}</strong> produkt{selectedKeys.length === 1 ? '' : 'er'} valgt
          <div style={mutedSmallStyle}>Kun de valgte produkter får genereret og reserveret Sæther Code.</div>
        </div>
        <button
          type="button"
          onClick={needsReservation ? onReserve : onPrepare}
          disabled={preparing || reserving || selectedKeys.length === 0}
          style={{ ...buttonStyle, background: preparing || reserving || selectedKeys.length === 0 ? '#9ca3af' : '#111827', cursor: preparing || reserving ? 'wait' : 'pointer' }}
        >
          {reserving
            ? 'Reserverer Sæther Code...'
            : (preparing
              ? 'Forbereder...'
              : (needsReservation ? 'Reservér Sæther Code' : 'Fortsæt til verificering'))}
        </button>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
    </div>
  )
}



function VerificationView({ verification, approval, onApproval, onBack }) {
  const [approving, setApproving] = useState(false)
  const [approvalError, setApprovalError] = useState(null)
  const [downloadingMasterdata, setDownloadingMasterdata] = useState(false)
  const [masterdataError, setMasterdataError] = useState(null)



  async function approveProducts() {
    if (!verification?.analysis_id) {
      setApprovalError('Analysis ID mangler. Gå tilbage og analysér filen igen.')
      return
    }



    setApproving(true)
    setApprovalError(null)



    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(verification.analysis_id)}/approve`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirmed: true }),
        }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Produkterne kunne ikke godkendes.')
      onApproval(data.approval)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setApprovalError(err.message)
    } finally {
      setApproving(false)
    }
  }




  async function downloadMasterdata() {
    const analysisId = approval?.analysis_id || verification?.analysis_id

    if (!analysisId) {
      setMasterdataError('Analysis ID mangler. Gå tilbage og analysér filen igen.')
      return
    }

    setDownloadingMasterdata(true)
    setMasterdataError(null)

    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysisId)}/masterdata.xlsx`
      )

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.detail || 'MASTERDATA-filen kunne ikke hentes.')
      }

      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      const disposition = response.headers.get('content-disposition') || ''
      const filenameMatch = disposition.match(
        /filename\*?=(?:UTF-8''|")?([^";]+)/i
      )
      const filename = filenameMatch
        ? decodeURIComponent(filenameMatch[1].replace(/^"|"$/g, ''))
        : `MASTERDATA_${analysisId}.xlsx`
      const link = document.createElement('a')

      link.href = objectUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
    } catch (err) {
      setMasterdataError(err.message)
    } finally {
      setDownloadingMasterdata(false)
    }
  }



  if (approval) {
    return (
      <section style={sectionStyle}>
        <div style={approvalSuccessStyle}>
          <div style={approvalSuccessTitleStyle}>Godkendelse gennemført</div>
          <div>
            {approval.ready_for_m3
              ? 'De godkendte produkter er klar til et senere M3-flow.'
              : 'Et eller flere produkter blev blokeret og er ikke klar til M3.'}
          </div>
        </div>



        <div style={analysisGridStyle}>
          <StatusCard label="Valgt" value={approval.requested_count} />
          <StatusCard label="Godkendt" value={approval.approved_count} color="#15803d" />
          <StatusCard label="Blokeret" value={approval.blocked_count} color={approval.blocked_count ? '#dc2626' : '#15803d'} />
          <StatusCard label="M3-status" value={approval.ready_for_m3 ? 'Klar' : 'Ikke klar'} color={approval.ready_for_m3 ? '#15803d' : '#dc2626'} />
        </div>




        <div style={masterdataExportStyle}>
          <div>
            <div style={masterdataTitleStyle}>MASTERDATA</div>
            <div style={masterdataStatusStyle}>
              {approval.ready_for_m3 && approval.approved_count > 0
                ? 'Klar til eksport'
                : 'Ikke klar til eksport'}
            </div>
            <div style={mutedSmallStyle}>
              Eksporten indeholder kun de godkendte produkter i denne analyse.
            </div>
          </div>
          <button
            type="button"
            onClick={downloadMasterdata}
            disabled={
              !approval.ready_for_m3 ||
              approval.approved_count === 0 ||
              downloadingMasterdata
            }
            style={{
              ...buttonStyle,
              background:
                !approval.ready_for_m3 ||
                approval.approved_count === 0 ||
                downloadingMasterdata
                  ? '#9ca3af'
                  : '#15803d',
              cursor: downloadingMasterdata ? 'wait' : 'pointer',
            }}
          >
            {downloadingMasterdata
              ? 'Henter MASTERDATA...'
              : 'Download MASTERDATA.xlsx'}
          </button>
        </div>
        {masterdataError && <ErrorBox>{masterdataError}</ErrorBox>}



        <div style={productListStyle}>
          {(approval.items || []).map((item) => (
            <div key={item.product_key} style={productCardStyle}>
              <div style={productHeaderStyle}>
                <div>
                  <div style={productCodeStyle}>{item.product_code || '-'}</div>
                  <div style={productNameStyle}>{item.product_name || '-'}</div>
                  <div style={eanStyle}>EAN {item.ean || '-'}</div>
                </div>
                <StatusBadge label={item.status} tone={item.status === 'APPROVED' ? 'green' : 'red'} />
              </div>
              <div style={verificationCodeStyle}>
                <span style={productFieldLabelStyle}>Sæther Code</span>
                <strong style={verificationCodeValueStyle}>{item.item_number || 'Mangler'}</strong>
              </div>
              {item.approved_at && (
                <div style={approvedMetaStyle}>
                  Godkendt {new Date(item.approved_at).toLocaleString('da-DK')} via {item.approval_source || 'user'}
                </div>
              )}
              {(item.errors || []).map((error) => <ErrorBox key={error}>{error}</ErrorBox>)}
            </div>
          ))}
        </div>



        <div style={verificationActionsStyle}>
          <button type="button" onClick={onBack} style={secondaryButtonStyle}>Tilbage til analyse</button>
        </div>
        <div style={approvalNoticeStyle}>Godkendt betyder klar til M3. Der er stadig ikke skrevet noget til M3.</div>
      </section>
    )
  }



  const hasMasterdataBlockers = (verification.items || []).some(
    (item) => (item.masterdata?.blocking_fields || []).length > 0
  )
  const canApprove = verification.can_continue && verification.blocked_count === 0 && verification.prepared_count > 0 && !hasMasterdataBlockers



  return (
    <section style={sectionStyle}>
      <h2 style={sectionTitleStyle}>Verificér produkter</h2>
      <p style={mutedStyle}>Kontrollér alle værdier og reserverede Sæther Codes. Der er endnu ikke godkendt eller sendt noget til M3.</p>
      <div style={analysisGridStyle}>
        <StatusCard label="Valgt" value={verification.requested_count} />
        <StatusCard label="Forberedt" value={verification.prepared_count} color="#15803d" />
        <StatusCard label="Blokeret" value={verification.blocked_count} color={verification.blocked_count ? '#dc2626' : '#15803d'} />
      </div>
      <DownloadReadinessPanel stage="verification" />
      <div style={productListStyle}>
        {(verification.items || []).map((item) => (
          <div key={item.product_key} style={productCardStyle}>
            <div style={productHeaderStyle}>
              <div>
                <div style={productCodeStyle}>{item.product_code || '-'}</div>
                <div style={productNameStyle}>{item.product_name || '-'}</div>
                <div style={eanStyle}>EAN {item.ean || '-'}</div>
              </div>
              <StatusBadge label={item.status} tone={item.status === 'PREPARED' ? 'green' : 'red'} />
            </div>
            <div style={verificationCodeStyle}>
              <span style={productFieldLabelStyle}>Reserveret Sæther Code</span>
              <strong style={verificationCodeValueStyle}>{item.item_number || 'Ikke genereret'}</strong>
            </div>
            <div style={productFieldsStyle}>
              <ProductField label="MMITTY" value={item.item_type} />
              <ProductField label="MMITGR" value={item.masterdata?.item_group || item.item_group} />
              <ProductField label="MMITCL" value={item.masterdata?.product_group || item.item_class} />
              <ProductField label="Product line" value={item.masterdata?.product_line} warning={!item.masterdata?.product_line} />
              <ProductField label="Item category" value={item.masterdata?.item_category} warning={!item.masterdata?.item_category} />
              <ProductField label="M3 navn / Line 1" value={item.masterdata?.m3_name} warning={!item.masterdata?.m3_name} />
            </div>
            <MasterDataGate masterdata={item.masterdata} />
            <details style={detailsStyle}>
              <summary style={detailsSummaryStyle}>Vis valgfrie felter og tekniske værdier</summary>
              <div style={productFieldsStyle}>
                <ProductField label="MMSTAT" value={item.mmstat} />
                <ProductField label="MMBUAR" value={item.brand_code} />
                <ProductField label="MMBUARTX40" value={item.brand_name} />
                <TextStatusProductField label="M3 beskrivelse / Line 2" resolution={item.masterdata?.text_resolution?.m3_description} value={item.masterdata?.m3_description} />
                <TextStatusProductField label="Bontekst" resolution={item.masterdata?.text_resolution?.receipt_text} value={item.masterdata?.receipt_text} />
              </div>
            </details>
            {(item.warnings || []).map((warning) => <div key={warning} style={warningStyle}>{warning}</div>)}
            {(item.errors || []).map((error) => <ErrorBox key={error}>{error}</ErrorBox>)}
          </div>
        ))}
      </div>
      {approvalError && <ErrorBox>{approvalError}</ErrorBox>}
      <div style={verificationActionsStyle}>
        <button type="button" onClick={onBack} disabled={approving} style={secondaryButtonStyle}>Tilbage til analyse</button>
        <button
          type="button"
          onClick={approveProducts}
          disabled={!canApprove || approving}
          style={{
            ...buttonStyle,
            background: !canApprove || approving ? '#9ca3af' : '#15803d',
            cursor: !canApprove ? 'not-allowed' : approving ? 'wait' : 'pointer',
          }}
        >
          {approving ? 'Godkender...' : `Godkend ${verification.prepared_count} produkter`}
        </button>
      </div>
      <div style={approvalNoticeStyle}>Godkendelsen revaliderer produkterne. Den skriver ikke noget til M3.</div>
    </section>
  )
}



function ConflictSection({ products }) {
  if (!products.length) {
    return null
  }

  return (
    <div style={productSectionStyle}>
      <h3 style={productSectionTitleStyle}>
        Kræver afklaring ({products.length})
      </h3>

      <p style={mutedStyle}>
        Disse produkter er blokeret, fordi
        identifikatorerne ikke stemmer sikkert
        overens med Golden Record.
      </p>

      <div style={productListStyle}>
        {products.map((product) => (
          <div
            key={
              product.ean ||
              product.product_code ||
              product.saether_code
            }
            style={conflictCardStyle}
          >
            <div style={productHeaderStyle}>
              <ProductHeader product={product} />

              <StatusBadge
                label="BLOKERET"
                tone="red"
              />
            </div>

            <div style={conflictMessageStyle}>
              {product.message}
            </div>

            <div style={productFieldsStyle}>
              <ProductField
                label="BMS Type"
                value={product.product_type}
              />

              <ProductField
                label="Indkommende EAN"
                value={product.ean}
              />

              <ProductField
                label="Indkommende Sæther Code"
                value={product.saether_code}
                warning
              />
            </div>

            {(product.golden_record_matches || []).map(
              (match, index) => (
                <div
                  key={`${match.item_number}-${index}`}
                  style={goldenRecordMatchStyle}
                >
                  <div style={reviewTitleStyle}>
                    Golden Record match
                  </div>

                  <div style={productFieldsStyle}>
                    <ProductField
                      label="MMITNO"
                      value={match.item_number}
                    />

                    <ProductField
                      label="EAN"
                      value={match.ean}
                      warning={
                        match.ean !== product.ean
                      }
                    />

                    <ProductField
                      label="MMITDS"
                      value={match.product_name}
                    />

                    <ProductField
                      label="MMITTY"
                      value={match.item_type}
                    />

                    <ProductField
                      label="MMITGR"
                      value={match.item_group}
                    />

                    <ProductField
                      label="MMITCL"
                      value={match.item_class}
                    />

                    <ProductField
                      label="MMBUAR"
                      value={match.brand_code}
                    />

                    <ProductField
                      label="MMSTAT"
                      value={match.mmstat}
                    />

                    <ProductField
                      label="Product Line"
                      value={match.product_line}
                    />
                  </div>
                </div>
              )
            )}

            <div style={conflictBlockedStyle}>
              Produktet kan ikke fortsætte til
              MMITNO-reservation, verificering eller
              godkendelse, før konflikten er afklaret.
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}




function ProductSection({ title, products, analysis, setAnalysis, onPromoted, onReserve, reserving, reserveError }) {
  if (!products.length) return null
  return (
    <div style={productSectionStyle}>
      <h3 style={productSectionTitleStyle}>{title}</h3>
      <div style={productListStyle}>
        {products.map((product) => (
          <div key={product.ean || product.product_code} style={productCardStyle}>
            <div style={productHeaderStyle}>
              <ProductHeader product={product} />
              <StatusBadge label="REVIEW" tone="amber" />
            </div>
            <LifecycleNextStep product={product} />
            {product.lifecycle?.can_reserve_code && (
              <button
                type="button"
                onClick={() => onReserve(product.ean || product.product_code)}
                disabled={reserving}
                style={{ ...buttonStyle, marginBottom: '14px', background: reserving ? '#9ca3af' : '#111827' }}
              >
                {reserving ? 'Reserverer...' : 'Bekræft ny vare og reservér Sæther Code'}
              </button>
            )}
            <ReviewEditor product={product} analysis={analysis} setAnalysis={setAnalysis} onPromoted={onPromoted} />
            {reserveError && <ErrorBox>{reserveError}</ErrorBox>}
          </div>
        ))}
      </div>
    </div>
  )
}



function ProductHeader({ product }) {
  return (
    <div>
      <div style={productCodeStyle}>{product.product_code || '-'}</div>
      <div style={productNameStyle}>{product.product_name || '-'}</div>
      <div style={eanStyle}>EAN {product.ean || '-'}</div>
      {product.saether_code && <div style={incomingCodeStyle}>Indkommende Sæther Code: <strong>{product.saether_code}</strong></div>}
    </div>
  )
}


function LifecycleNextStep({ product }) {
  const lifecycle = product.lifecycle || {}
  if (!lifecycle.stage) return null
  return (
    <div style={lifecycleNextStepStyle}>
      <strong>{lifecycle.label}</strong>
      <span>Næste trin: {lifecycle.next_action}</span>
      {(lifecycle.blockers || []).length > 0 && (
        <span>Blokerer: {(lifecycle.blockers || []).map(fieldLabel).join(', ')}</span>
      )}
    </div>
  )
}



function ReadyFields({ product }) {
  const masterdata = product.masterdata || {}
  const evidenceNumbers = masterdata.evidence?.item_numbers || masterdata.evidence_item_numbers || []
  const warnings = masterdata.warning_fields || []
  return (
    <>
      <div style={reviewFirstPanelStyle}>
        <div style={reviewFirstHeaderStyle}>
          <div>
            <div style={readyForSkuStyle}>Klar til SKU</div>
            <div style={automaticTitleStyle}>Automatisk klassificeret</div>
          </div>
          <StatusBadge label="READY" tone="green" />
        </div>
        <div style={automaticGridStyle}>
          <AutomaticField
            label="Sæther Code"
            value={product.item_number}
            missingLabel="Genereres ved verificering"
          />
          <AutomaticField label="Item type" value={masterdata.item_type || product.item_type} />
          <AutomaticField label="Item group" value={masterdata.item_group || product.item_group} />
          <AutomaticField label="Product group" value={masterdata.product_group || product.item_class} />
          <AutomaticField label="Product line" value={masterdata.product_line} overridden={(masterdata.override_fields || []).includes('product_line')} />
          <AutomaticField label="Item category" value={masterdata.item_category} overridden={(masterdata.override_fields || []).includes('item_category')} />
          <TextResolutionField label="M3 navn / Line 1" resolution={masterdata.text_resolution?.m3_name} value={masterdata.m3_name} overridden={(masterdata.override_fields || []).includes('m3_name')} />
          <TextResolutionField label="M3 beskrivelse / Line 2" resolution={masterdata.text_resolution?.m3_description} value={masterdata.m3_description} />
          <TextResolutionField label="Bontekst" resolution={masterdata.text_resolution?.receipt_text} value={masterdata.receipt_text} />
        </div>
        <div style={evidenceInlineStyle}>
          Evidens: <strong>{evidenceNumbers.length ? evidenceNumbers.join(', ') : 'ingen entydig sibling'}</strong>
        </div>
        {warnings.length > 0 && (
          <div style={optionalMissingStyle}>
            <strong>Valgfrie mangler</strong> · {warnings.map(fieldLabel).join(', ')}
          </div>
        )}
      </div>
      <MasterDataGate masterdata={masterdata} />
    </>
  )
}


function AutomaticField({ label, value, overridden = false, missingLabel = 'Kræver review' }) {
  const missing = value === null || value === undefined || value === ''
  return (
    <div style={automaticFieldStyle}>
      <span style={{ ...automaticCheckStyle, color: missing ? '#b45309' : '#15803d' }}>{missing ? '○' : '✓'}</span>
      <span>
        <span style={automaticFieldLabelStyle}>{label}</span>{' '}
        <strong>{missing ? missingLabel : String(value)}</strong>
        {overridden && <span style={overrideBadgeStyle}>Manuel override</span>}
      </span>
    </div>
  )
}


const textSourceLabels = {
  reviewed_value: 'Manuelt review',
  supplier_product_name: 'Leverandørfil',
  supplier_line_2: 'Leverandørfil',
  supplier_receipt_text: 'Leverandørfil',
  golden_record_sibling: 'Golden Record-sibling',
  item_type_rule: 'Varetyperegel',
}


function TextResolutionField({ label, resolution = {}, value, overridden = false }) {
  const resolvedValue = resolution.value ?? value
  const status = resolution.status || (resolvedValue ? 'documented' : 'missing_documented_source')
  const notApplicable = status === 'not_applicable'
  const awaitingItemType = status === 'awaiting_item_type'
  const missing = resolvedValue === null || resolvedValue === undefined || resolvedValue === ''
  const marker = notApplicable ? '–' : (awaitingItemType ? '…' : (missing ? '○' : '✓'))
  const display = awaitingItemType
    ? 'Afventer varetype'
    : (notApplicable
      ? 'Ikke relevant for varetype 12'
      : (missing ? 'Ingen dokumenteret værdi fundet' : String(resolvedValue)))
  const source = textSourceLabels[resolution.source]
  const reviewLabel = missing && !notApplicable && !awaitingItemType
    ? (resolution.required ? 'Påkrævet review' : 'Valgfrit review')
    : null

  return (
    <div style={automaticFieldStyle}>
      <span style={{ ...automaticCheckStyle, color: notApplicable ? '#6b7280' : (missing ? '#b45309' : '#15803d') }}>{marker}</span>
      <span>
        <span style={automaticFieldLabelStyle}>{label}</span>{' '}
        <strong>{display}</strong>
        {source && <span style={textSourceStyle}>Kilde: {source}</span>}
        {reviewLabel && <span style={textReviewStyle}>{reviewLabel}</span>}
        {overridden && <span style={overrideBadgeStyle}>Manuel override</span>}
      </span>
    </div>
  )
}


const masterdataFieldLabels = {
  brand_code: 'brandkode (MMBUAR)',
  brand_name: 'brandnavn (MMBUARTX40)',
  ean: 'EAN',
  item_number: 'Sæther Code',
  item_type: 'MMITTY',
  item_group: 'MMITGR',
  item_group_description: 'item-group-beskrivelse',
  product_group: 'MMITCL',
  product_line: 'Product line',
  item_category: 'Item category',
  m3_name: 'M3 navn / Line 1',
  m3_description: 'M3 beskrivelse / Line 2',
  receipt_text: 'bontekst',
  ref_number: 'leverandørreference',
}


function fieldLabel(fieldName) {
  return masterdataFieldLabels[fieldName] || fieldName.replaceAll('_', ' ')
}


function MasterDataEvidence({ masterdata = {} }) {
  const evidence = masterdata.evidence || {}
  const evidenceNumbers = evidence.item_numbers || masterdata.evidence_item_numbers || []

  return (
    <div style={evidencePanelStyle}>
      <div style={productFieldsStyle}>
        <TextStatusProductField label="M3 navn / Line 1" resolution={masterdata.text_resolution?.m3_name} value={masterdata.m3_name} />
        <TextStatusProductField label="M3 beskrivelse / Line 2" resolution={masterdata.text_resolution?.m3_description} value={masterdata.m3_description} />
        <TextStatusProductField label="Bontekst" resolution={masterdata.text_resolution?.receipt_text} value={masterdata.receipt_text} />
        <ProductField label="Product line" value={masterdata.product_line} />
        <ProductField label="Product line-beskrivelse" value={masterdata.product_line_description || evidence.product_line_description} />
        <ProductField label="Item category" value={masterdata.item_category} />
        <ProductField label="Item-group-evidens" value={masterdata.item_group_evidence_description || evidence.item_group_description} />
        <ProductField label="Product-group-evidens" value={masterdata.product_group_description || evidence.product_group_description} />
      </div>
      <div style={evidenceSourceStyle}>
        Golden Record-evidens: <strong>{evidenceNumbers.length ? evidenceNumbers.join(', ') : 'ingen entydig sibling'}</strong>
      </div>
    </div>
  )
}


function MasterDataGate({ masterdata = {} }) {
  const blocking = masterdata.blocking_fields || []
  const warnings = masterdata.warning_fields || []

  if (blocking.length > 0) {
    return <div style={blockingStyle}>Kræves før godkendelse: {blocking.join(', ')}</div>
  }
  if (warnings.length > 0) {
    return (
      <details style={optionalWarningDetailsStyle}>
        <summary style={optionalWarningSummaryStyle}>
          Klar til verificering · {warnings.length} valgfri{warnings.length === 1 ? 't' : 'e'} advarsel{warnings.length === 1 ? '' : 'er'}
        </summary>
        <div style={optionalWarningBodyStyle}>
          Kan udfyldes senere og blokerer ikke SKU-oprettelse: {warnings.map(fieldLabel).join(', ')}.
        </div>
      </details>
    )
  }
  return <div style={gateReadyStyle}>Minimumskrav opfyldt · klar til verificering</div>
}



function MasterDataReviewEditor({ product, analysis, setAnalysis, reviewMode = false, onPromoted }) {
  const masterdata = product.masterdata || {}
  const [m3Name, setM3Name] = useState(masterdata.m3_name || '')
  const [m3Description, setM3Description] = useState(masterdata.m3_description || '')
  const [receiptText, setReceiptText] = useState(masterdata.receipt_text || '')
  const [itemGroup, setItemGroup] = useState(masterdata.item_group || '')
  const [itemClass, setItemClass] = useState(masterdata.product_group || '')
  const [productLine, setProductLine] = useState(masterdata.product_line || '')
  const [itemCategory, setItemCategory] = useState(masterdata.item_category || '')
  const [overrideMode, setOverrideMode] = useState(false)
  const [overrideFields, setOverrideFields] = useState(masterdata.override_fields || [])
  const [overrideReason, setOverrideReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [savedSummary, setSavedSummary] = useState(null)
  const receiptResolution = masterdata.text_resolution?.receipt_text || {}
  const receiptNotApplicable = receiptResolution.status === 'not_applicable'
  const receiptAwaitingItemType = receiptResolution.status === 'awaiting_item_type'
  const receiptRequired = Boolean(receiptResolution.required)

  useEffect(() => {
    setM3Name(masterdata.m3_name || '')
    setM3Description(masterdata.m3_description || '')
    setReceiptText(masterdata.receipt_text || '')
    setItemGroup(masterdata.item_group || '')
    setItemClass(masterdata.product_group || '')
    setProductLine(masterdata.product_line || '')
    setItemCategory(masterdata.item_category || '')
    setOverrideFields(masterdata.override_fields || [])
  }, [
    masterdata.m3_name,
    masterdata.m3_description,
    masterdata.receipt_text,
    masterdata.item_group,
    masterdata.product_group,
    masterdata.product_line,
    masterdata.item_category,
    masterdata.override_fields,
  ])

  const automaticValues = masterdata.automatic_values || {}
  const itemGroupOptions = normalizeOverrideOptions(masterdata.item_group_options || [])
  const itemClassOptions = normalizeOverrideOptions(masterdata.item_class_options || [])
  const itemCategoryOptions = normalizeOverrideOptions(
    masterdata.item_category_option_details || masterdata.item_category_options
  )
  const productLineOptions = normalizeOverrideOptions(
    masterdata.product_line_option_details || masterdata.product_line_options
  )
  const isOverridden = (fieldName) => (masterdata.override_fields || []).includes(fieldName)
  const isSelected = (fieldName) => overrideFields.includes(fieldName)
  const toggleOverride = (fieldName) => {
    setOverrideFields((current) => current.includes(fieldName)
      ? current.filter((item) => item !== fieldName)
      : [...current, fieldName])
  }

  async function postMasterdataReview(body) {
    if (!analysis?.analysis_id) throw new Error('Analysis ID mangler. Upload filen igen.')
    const productKey = product.ean || product.product_code
    if (!productKey) throw new Error('Produktet mangler både EAN og produktkode.')
    const response = await fetch(
      `/api/reviews/${encodeURIComponent(analysis.analysis_id)}/${encodeURIComponent(productKey)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    )
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'MASTERDATA-review kunne ikke gemmes.')
    setAnalysis(data.analysis)
    setSavedSummary(data.review_summary || null)
    if (data.ready && onPromoted) onPromoted(productKey)
    return data
  }

  async function saveMasterdataReview() {
    const body = {
      masterdata_review: true,
      override_fields: overrideFields,
      override_reason: overrideFields.length ? overrideReason.trim() || null : null,
    }
    if (isSelected('m3_name') || !automaticValues.m3_name) body.m3_name = m3Name.trim() || null
    if (isSelected('item_group') || !automaticValues.item_group) body.item_group = itemGroup.trim() || null
    if (isSelected('product_group') || !automaticValues.product_group) body.item_class = itemClass.trim() || null
    if (isSelected('product_line') || !automaticValues.product_line) body.product_line = productLine.trim() || null
    if (isSelected('item_category') || !automaticValues.item_category) body.item_category = itemCategory.trim() || null
    if (!masterdata.m3_description && m3Description.trim()) body.m3_description = m3Description.trim()
    if (!receiptNotApplicable && !receiptAwaitingItemType && !masterdata.receipt_text && receiptText.trim()) body.receipt_text = receiptText.trim()
    if (!Object.keys(body).some((key) => !['masterdata_review', 'override_fields', 'override_reason'].includes(key))) {
      return setError('Vælg en override eller udfyld et reelt manglende felt.')
    }
    setSaving(true)
    setSavedSummary(null)
    setError(null)
    try {
      await postMasterdataReview(body)
      setOverrideMode(false)
      setOverrideReason('')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function resetOverride(fieldName) {
    setSaving(true)
    setSavedSummary(null)
    setError(null)
    try {
      await postMasterdataReview({
        masterdata_review: true,
        reset_override_fields: [fieldName],
      })
      setOverrideFields((current) => current.filter((item) => item !== fieldName))
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      {savedSummary && <SavedReviewSummary summary={savedSummary} />}
      {(masterdata.override_fields || []).length > 0 && (
        <div style={activeOverridesStyle}>
          <strong>Aktive overrides</strong>
          {(masterdata.override_fields || []).map((fieldName) => (
            <button key={fieldName} type="button" onClick={() => resetOverride(fieldName)} disabled={saving} style={resetOverrideButtonStyle}>
              Nulstil override · {fieldLabel(fieldName)}
            </button>
          ))}
        </div>
      )}
      {!overrideMode ? (
        <button type="button" onClick={() => setOverrideMode(true)} style={overrideActionStyle}>
          {reviewMode ? 'Udfyld manglende oplysninger' : 'Ret foreslåede værdier'}
        </button>
      ) : (
        <div style={overridePanelStyle}>
          <div style={overridePanelTitleStyle}>Manuel override</div>
          <div style={mutedSmallStyle}>Vælg kun et felt, når den automatiske mapping er dokumenteret forkert. Den automatiske værdi og evidens bevares, så du altid kan nulstille.</div>
          <OverrideField label="M3 navn / Line 1" fieldName="m3_name" selected={isSelected('m3_name')} onToggle={toggleOverride} automaticValue={automaticValues.m3_name}>
            <ReviewInput label={`Ny værdi (${m3Name.length}/30)`} value={m3Name} onChange={setM3Name} required={isSelected('m3_name')} disabled={!isSelected('m3_name')} />
          </OverrideField>
          <OverrideSelectField
            label="MMITGR"
            fieldName="item_group"
            selected={isSelected('item_group')}
            onToggle={toggleOverride}
            automaticValue={automaticValues.item_group}
            value={itemGroup}
            onChange={setItemGroup}
            options={itemGroupOptions}
            placeholder="Vælg dokumenteret item group"
          />
          <OverrideSelectField
            label="MMITCL"
            fieldName="product_group"
            selected={isSelected('product_group')}
            onToggle={toggleOverride}
            automaticValue={automaticValues.product_group}
            value={itemClass}
            onChange={setItemClass}
            options={itemClassOptions}
            placeholder="Vælg dokumenteret item class"
          />
          <OverrideSelectField
            label="Product line"
            fieldName="product_line"
            selected={isSelected('product_line')}
            onToggle={toggleOverride}
            automaticValue={automaticValues.product_line}
            value={productLine}
            onChange={setProductLine}
            options={productLineOptions}
            placeholder="Vælg product line"
          />
          <OverrideSelectField
            label="Item category"
            fieldName="item_category"
            selected={isSelected('item_category')}
            onToggle={toggleOverride}
            automaticValue={automaticValues.item_category}
            value={itemCategory}
            onChange={setItemCategory}
            options={itemCategoryOptions}
            placeholder="Vælg fra Data for drop downs"
          />
          {overrideFields.length > 0 && (
            <label>
              <span style={reviewInputLabelStyle}>Begrundelse for override <span style={requiredStyle}>Påkrævet</span></span>
              <textarea value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} rows={3} style={reviewTextareaStyle} />
            </label>
          )}
          {(!masterdata.m3_description || (!receiptNotApplicable && !receiptAwaitingItemType && !masterdata.receipt_text)) && (
            <details style={detailsStyle}>
              <summary style={detailsSummaryStyle}>Udfyld dokumenterede tekstmangler</summary>
              <div style={reviewGridStyle}>
                {!masterdata.m3_description && <ReviewInput label={`M3 beskrivelse / Line 2 – valgfri (${m3Description.length}/60)`} value={m3Description} onChange={setM3Description} required={false} disabled={false} />}
                {!receiptNotApplicable && !receiptAwaitingItemType && !masterdata.receipt_text && <ReviewInput label={`Bontekst${receiptRequired ? ' – påkrævet for salgsvare' : ' – valgfri'} (${receiptText.length}/20)`} value={receiptText} onChange={setReceiptText} required={receiptRequired} disabled={false} />}
              </div>
            </details>
          )}
          {error && <ErrorBox>{error}</ErrorBox>}
          <div style={reviewActionsStyle}>
            <button type="button" onClick={saveMasterdataReview} disabled={saving || m3Name.length > 30 || m3Description.length > 60 || receiptText.length > 20 || (overrideFields.length > 0 && !overrideReason.trim())} style={{ ...buttonStyle, background: saving ? '#9ca3af' : '#111827' }}>
              {saving ? 'Gemmer og genberegner...' : 'Gem override'}
            </button>
            <button type="button" onClick={() => { setOverrideMode(false); setError(null) }} disabled={saving} style={secondaryButtonStyle}>Annuller</button>
          </div>
        </div>
      )}
    </>
  )
}


function OverrideField({ label, fieldName, selected, onToggle, automaticValue, children }) {
  return (
    <div style={overrideFieldStyle}>
      <label style={checkboxLabelStyle}>
        <input type="checkbox" checked={selected} onChange={() => onToggle(fieldName)} />
        <span>Overstyr {label}</span>
      </label>
      <div style={automaticValueStyle}>Automatisk værdi: <strong>{automaticValue || 'ikke dokumenteret'}</strong></div>
      <div style={overrideControlStyle}>{children}</div>
    </div>
  )
}


function normalizeOverrideOptions(rawOptions) {
  const seen = new Set()
  return (Array.isArray(rawOptions) ? rawOptions : [])
    .map((option) => {
      if (typeof option === 'string') return { value: option, label: option }
      if (!option || typeof option !== 'object') return null
      const value = String(option.value || '').trim()
      if (!value) return null
      return { value, label: String(option.label || value) }
    })
    .filter((option) => {
      if (!option || seen.has(option.value)) return false
      seen.add(option.value)
      return true
    })
}


function OverrideSelectField({ label, fieldName, selected, onToggle, automaticValue, value, onChange, options, placeholder }) {
  const selectableOptions = [...options]
  if (value && !selectableOptions.some((option) => option.value === value)) {
    selectableOptions.unshift({ value, label: `${value} (nuværende værdi)` })
  }
  return (
    <div style={overrideFieldStyle}>
      <div style={overrideFieldHeaderStyle}>
        <div>
          <div style={overrideFieldLabelStyle}>{label}</div>
          <div style={automaticValueStyle}>Automatisk værdi: <strong>{automaticValue || 'ikke dokumenteret'}</strong></div>
        </div>
        <button type="button" onClick={() => onToggle(fieldName)} style={selected ? cancelOverrideButtonStyle : enableOverrideButtonStyle}>
          {selected ? 'Annuller override' : `Aktivér override af ${label}`}
        </button>
      </div>
      {selected && (
        <select
          aria-label={`${label} override`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          style={reviewSelectStyle}
        >
          <option value="">{placeholder}</option>
          {selectableOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      )}
      {selected && selectableOptions.length === 0 && (
        <div style={overrideOptionsErrorStyle}>Ingen valgmuligheder blev indlæst fra template-referencefilen.</div>
      )}
    </div>
  )
}


function SavedReviewSummary({ summary }) {
  const values = summary.values || {}
  const textResolution = summary.text_resolution || {}
  const evidenceNumbers = summary.evidence?.item_numbers || []
  const warnings = summary.warning_fields || []
  const blockers = summary.blocking_fields || []

  return (
    <div style={savedSummaryStyle} role="status">
      <div style={savedSummaryTitleStyle}>Gemt · preview er genberegnet</div>
      <div style={savedValuesGridStyle}>
        <ProductField label="M3 navn / Line 1" value={values.m3_name} />
        <TextStatusProductField label="M3 beskrivelse / Line 2" resolution={textResolution.m3_description} value={values.m3_description} />
        <TextStatusProductField label="Bontekst" resolution={textResolution.receipt_text} value={values.receipt_text} />
        <ProductField label="MMITGR" value={values.item_group} />
        <ProductField label="MMITCL" value={values.product_group} />
        <ProductField label="Product line" value={values.product_line} />
        <ProductField label="Item category" value={values.item_category} />
      </div>
      <div style={savedSummaryMetaStyle}>
        Golden Record-evidens: <strong>{evidenceNumbers.length ? evidenceNumbers.join(', ') : 'ingen entydig sibling'}</strong>
      </div>
      {warnings.length > 0 && (
        <div style={savedSummaryMetaStyle}>Valgfrit og ikke-blokerende: {warnings.map(fieldLabel).join(', ')}.</div>
      )}
      {blockers.length > 0 && (
        <div style={blockingInlineStyle}>Mangler før verificering: {blockers.map(fieldLabel).join(', ')}.</div>
      )}
      <div style={savedNextStepStyle}>Næste trin: {summary.next_step}</div>
    </div>
  )
}


function ReviewEditor({ product, analysis, setAnalysis, onPromoted }) {
  const masterdata = product.masterdata || {}
  const [itemType, setItemType] = useState(product.item_type || '')
  const [itemGroup, setItemGroup] = useState(product.item_group || masterdata.item_group || '')
  const [itemClass, setItemClass] = useState(product.item_class || masterdata.product_group || '')
  const [productLine, setProductLine] = useState(product.product_line || masterdata.product_line || '')
  const [brandValue, setBrandValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const brandMissing = !product.brand_code || !product.brand_name
  const brandOptions = normalizeOverrideOptions(analysis.brand_options || [])
  const itemTypeOptions = normalizeOverrideOptions(masterdata.item_type_options || [])
  const blockerNames = (masterdata.blocking_fields || []).map((field) => field === 'product_group' ? 'item_class' : field)
  const missing = Array.from(new Set([
    ...(product.needs_review || []).filter((field) => field !== 'item_number'),
    ...blockerNames,
  ]))
  const isMissing = (fieldName) => missing.includes(fieldName)
  const getSuggestion = (fieldName) => (product.suggestions || []).find((item) => item.field_name === fieldName)
  const useSuggestion = (fieldName, setter) => {
    const suggestion = getSuggestion(fieldName)
    if (suggestion) setter(suggestion.suggested_value)
  }

  useEffect(() => {
    setItemType(product.item_type || '')
    setItemGroup(product.item_group || masterdata.item_group || '')
    setItemClass(product.item_class || masterdata.product_group || '')
    setProductLine(product.product_line || masterdata.product_line || '')
  }, [
    product.item_type,
    product.item_group,
    product.item_class,
    product.product_line,
    masterdata.item_group,
    masterdata.product_group,
    masterdata.product_line,
  ])

  async function postReview(body) {
    if (!analysis.analysis_id) throw new Error('Analysis ID mangler. Upload filen igen.')
    const productKey = product.ean || product.product_code
    if (!productKey) throw new Error('Produktet mangler både EAN og produktkode.')
    const response = await fetch(
      `/api/reviews/${encodeURIComponent(analysis.analysis_id)}/${encodeURIComponent(productKey)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    )
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Review kunne ikke gemmes.')
    setAnalysis(data.analysis)
    if (data.ready && onPromoted) onPromoted(productKey)
    return data
  }

  async function saveBrand() {
    const selected = (analysis.brand_options || []).find((option) => option.value === brandValue)
    if (!selected) return setError('Vælg et dokumenteret brand fra Golden Record.')
    setSaving(true)
    setError(null)
    try {
      await postReview({ brand_code: selected.code, brand_name: selected.name })
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function saveReview() {
    const body = {
      item_type: isMissing('item_type') ? itemType.trim() || null : null,
      item_group: isMissing('item_group') ? itemGroup.trim() || null : null,
      item_class: isMissing('item_class') ? itemClass.trim() || null : null,
      product_line: isMissing('product_line') ? productLine.trim() || null : null,
    }
    if (!Object.values(body).some(Boolean)) return setError('Vælg mindst én dokumenteret manglende værdi.')
    setSaving(true)
    setError(null)
    try {
      await postReview(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (brandMissing) {
    return (
      <>
        <div style={productFieldsStyle}>
          <ProductField label="BMS Type" value={product.product_type} />
          <ProductField label="MMSTAT" value={product.mmstat} />
          <ProductField label="MMBUAR" value={null} warning />
          <ProductField label="Family Match" value={product.family_match} />
        </div>
        <div style={reviewPanelStyle}>
          <div style={reviewTitleStyle}>1. Identificér brand</div>
          <p style={mutedSmallStyle}>Brandkode og brandnavn er blokerende minimumskrav. Vælg et observeret MMBUAR/MMBUARTX40-par; derefter genklassificerer backend produktet mod dette brands Golden Record-familier.</p>
          <SearchableDocumentedSelect
            label="Brand (MMBUAR / MMBUARTX40)"
            value={brandValue}
            onChange={setBrandValue}
            options={brandOptions}
            placeholder="Søg og vælg brand"
            required
          />
          {error && <ErrorBox>{error}</ErrorBox>}
          <div style={reviewActionsStyle}>
            <button type="button" onClick={saveBrand} disabled={saving || !brandValue} style={{ ...buttonStyle, background: saving || !brandValue ? '#9ca3af' : '#111827' }}>
              {saving ? 'Genklassificerer...' : 'Vælg brand og genklassificér'}
            </button>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <div style={productFieldsStyle}>
        <ProductField label="BMS Type" value={product.product_type} />
        <ProductField label="MMSTAT" value={product.mmstat} />
        <ProductField label="MMBUAR" value={`${product.brand_code} — ${product.brand_name}`} />
        <ProductField label="Family Match" value={product.family_match} />
      </div>
      <div style={reviewPanelStyle}>
        <div style={reviewTitleStyle}>Udfyld manglende oplysninger</div>
        <p style={mutedSmallStyle}>Sæther Code kræver kun sikker identitet og brand. Den kontrollerede familie vælges samlet; MMITGR/MMITCL kan ikke kombineres vilkårligt.</p>
        <div style={reviewGridStyle}>
          <SearchableDocumentedSelect label="MMITTY" value={itemType} onChange={setItemType} options={itemTypeOptions} placeholder="Vælg dokumenteret varetype" required={isMissing('item_type')} disabled={!isMissing('item_type')} />
          <SearchableDocumentedSelect label="MMITGR" value={itemGroup} onChange={() => {}} options={[]} placeholder="Vælges via familie" required={isMissing('item_group')} disabled />
          <SearchableDocumentedSelect label="MMITCL" value={itemClass} onChange={() => {}} options={[]} placeholder="Vælges via familie" required={isMissing('item_class')} disabled />
          <SearchableDocumentedSelect label="Product Line" value={productLine} onChange={() => {}} options={[]} placeholder="Afledes fra brand + template" required={isMissing('product_line')} disabled />
        </div>
        {(masterdata.family_candidates || []).length > 0 && (isMissing('item_group') || isMissing('item_class')) && (
          <FamilyCandidates
            candidates={masterdata.family_candidates}
            ambiguous={masterdata.ambiguous}
            onChoose={(candidate) => {
              setItemGroup(candidate.item_group)
              setItemClass(candidate.item_class)
            }}
          />
        )}
        {missing.length > 0 && <p style={missingStyle}>Blokerer fortsat: {missing.map(fieldLabel).join(', ')}</p>}
        {error && <ErrorBox>{error}</ErrorBox>}
        <div style={reviewActionsStyle}>
          <button type="button" onClick={saveReview} disabled={saving} style={{ ...buttonStyle, background: saving ? '#9ca3af' : '#111827', cursor: saving ? 'wait' : 'pointer' }}>
            {saving ? 'Gemmer og kontrollerer minimumskrav...' : 'Gem oplysninger'}
          </button>
        </div>
      </div>
      <MasterDataReviewEditor
        product={product}
        analysis={analysis}
        setAnalysis={setAnalysis}
        reviewMode
        onPromoted={onPromoted}
      />
    </>
  )
}


function SearchableDocumentedSelect({ label, value, onChange, options, placeholder, required = false, disabled = false }) {
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLocaleLowerCase('da-DK')
  const filtered = normalizedQuery
    ? options.filter((option) => option.label.toLocaleLowerCase('da-DK').includes(normalizedQuery))
    : options
  const selectable = [...filtered]
  if (value && !selectable.some((option) => option.value === value)) {
    const current = options.find((option) => option.value === value)
    if (current) selectable.unshift(current)
  }

  return (
    <div style={reviewInputWrapperStyle}>
      <label>
        <span style={reviewInputLabelStyle}>{label}{required && <span style={requiredStyle}>{' '}Mangler</span>}</span>
        {!disabled && (
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={placeholder}
            style={{ ...reviewInputStyle, marginTop: '6px' }}
          />
        )}
        <select
          aria-label={label}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          style={{ ...reviewSelectStyle, marginTop: '6px', background: disabled ? '#f3f4f6' : '#ffffff', borderColor: required ? '#f59e0b' : '#d1d5db' }}
        >
          <option value="">{disabled ? (value || 'Ikke redigerbar') : placeholder}</option>
          {selectable.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      {!disabled && options.length === 0 && <div style={overrideOptionsErrorStyle}>Ingen dokumenterede valgmuligheder blev fundet.</div>}
    </div>
  )
}


function FamilyCandidates({ candidates, ambiguous, onChoose }) {
  return (
    <div style={familyCandidatesStyle}>
      <div style={reviewTitleStyle}>{ambiguous ? 'Vælg blandt de bedst dokumenterede familier' : 'Rangerede dokumenterede familier'}</div>
      <p style={mutedSmallStyle}>Kun top 3 vises i hovedflowet. Valget udfylder MMITGR, MMITCL og evidensbaseret Item category samlet.</p>
      {candidates.slice(0, 3).map((candidate) => (
        <button key={candidate.value} type="button" onClick={() => onChoose(candidate)} style={familyCandidateButtonStyle}>
          <strong>{candidate.label}</strong>
          <span>{candidate.confidence || 0}% match · {candidate.count} Golden Record-referencer</span>
          <span>{(candidate.reasons || []).join(' · ')}</span>
          <span>Evidens: {(candidate.evidence_item_numbers || []).slice(0, 3).join(', ') || 'ingen varenummer-eksempler'}</span>
        </button>
      ))}
    </div>
  )
}


function ReviewInput({ label, value, onChange, required, disabled, suggestion, onUseSuggestion }) {
  return (
    <div style={reviewInputWrapperStyle}>
      <label>
        <span style={reviewInputLabelStyle}>{label}{required && <span style={requiredStyle}>{' '}Mangler</span>}</span>
        <input type="text" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} style={{ ...reviewInputStyle, marginTop: '6px', background: disabled ? '#f3f4f6' : '#ffffff', borderColor: required ? '#f59e0b' : '#d1d5db' }} />
      </label>
      {!disabled && suggestion && <SuggestionBox suggestion={suggestion} onUse={onUseSuggestion} />}
      {!disabled && !suggestion && <div style={noSuggestionStyle}>Ingen tidligere godkendelser i samme kontekst</div>}
    </div>
  )
}



function SuggestionBox({ suggestion, onUse }) {
  const count = suggestion.evidence_count || 0
  const strong = count >= 3
  return (
    <div style={{ ...suggestionBoxStyle, borderColor: strong ? '#86efac' : '#bfdbfe', background: strong ? '#f0fdf4' : '#eff6ff' }}>
      <div style={suggestionTitleStyle}>Tidligere feedback</div>
      <div>Forslag: <strong>{suggestion.suggested_value}</strong></div>
      <div style={suggestionEvidenceStyle}>{count} tidligere godkendelse{count === 1 ? '' : 'r'} i samme kontekst</div>
      {strong && <div style={strongEvidenceStyle}>{count >= 5 ? 'Kandidat til automatisk udfyldning' : 'Stærk historisk evidens'}</div>}
      <button type="button" onClick={onUse} style={suggestionButtonStyle}>Brug forslag</button>
    </div>
  )
}


function WorkflowProgress({ stage }) {
  const stages = [
    { key: 'analysis', number: 1, label: 'Analyse' },
    { key: 'code', number: 2, label: 'Identitet & Sæther Code' },
    { key: 'masterdata', number: 3, label: 'MASTERDATA-review' },
    { key: 'verification', number: 4, label: 'Verificering' },
    { key: 'approval', number: 5, label: 'Godkendelse' },
    { key: 'download', number: 6, label: 'Download' },
  ]
  const currentIndex = stage === 'download' ? 5 : stage === 'approval' ? 4 : stage === 'verification' ? 3 : 0

  return (
    <section style={workflowStyle} aria-label="Workflow">
      {stages.map((item, index) => {
        const completed = index < currentIndex
        const active = index === currentIndex
        return (
          <div key={item.key} style={{ ...workflowStepStyle, opacity: index > currentIndex ? 0.55 : 1 }}>
            <div style={{ ...workflowNumberStyle, background: completed ? '#15803d' : active ? '#111827' : '#e5e7eb', color: completed || active ? '#ffffff' : '#6b7280' }}>
              {completed ? '✓' : item.number}
            </div>
            <div>
              <div style={workflowStepLabelStyle}>{item.label}</div>
              {item.key === 'download' && index > currentIndex && <div style={workflowStepHintStyle}>Efter godkendelse</div>}
            </div>
          </div>
        )
      })}
    </section>
  )
}


function DownloadReadinessPanel({ stage }) {
  const onVerification = stage === 'verification'
  return (
    <div style={downloadReadinessStyle}>
      <div>
        <div style={masterdataTitleStyle}>MASTERDATA.xlsx</div>
        <div style={downloadReadinessTitleStyle}>Download låses op efter godkendelse</div>
        <div style={mutedSmallStyle}>
          {onVerification
            ? 'Kontrollér de reserverede Sæther Codes og godkend produkterne. Derefter vises download-knappen her i flowet.'
            : 'Vælg produkter, fortsæt til verificering og godkend dem. Eksporten bliver først tilgængelig, når approval-gaten er bestået.'}
        </div>
      </div>
      <button type="button" disabled style={disabledDownloadButtonStyle}>Download MASTERDATA.xlsx</button>
    </div>
  )
}


function ProductField({ label, value, warning = false }) {
  const missing = value === null || value === undefined || value === ''
  return (
    <div style={productFieldStyle}>
      <div style={productFieldLabelStyle}>{label}</div>
      <div style={{ ...productFieldValueStyle, color: warning || missing ? '#b45309' : '#1f2937' }}>{missing ? 'Mangler' : String(value)}</div>
    </div>
  )
}


function TextStatusProductField({ label, resolution = {}, value }) {
  const resolvedValue = resolution.value ?? value
  const status = resolution.status || (resolvedValue ? 'documented' : 'missing_documented_source')
  const notApplicable = status === 'not_applicable'
  const awaitingItemType = status === 'awaiting_item_type'
  const missing = resolvedValue === null || resolvedValue === undefined || resolvedValue === ''
  const display = awaitingItemType
    ? 'Afventer varetype'
    : (notApplicable
      ? 'Ikke relevant for varetype 12'
      : (missing ? 'Ingen dokumenteret værdi fundet' : String(resolvedValue)))
  const source = textSourceLabels[resolution.source]

  return (
    <div style={productFieldStyle}>
      <div style={productFieldLabelStyle}>{label}</div>
      <div style={{ ...productFieldValueStyle, color: notApplicable ? '#6b7280' : (missing ? '#b45309' : '#1f2937') }}>{display}</div>
      {source && <div style={productFieldMetaStyle}>Kilde: {source}</div>}
      {missing && !notApplicable && !awaitingItemType && <div style={productFieldMetaStyle}>{resolution.required ? 'Påkrævet review' : 'Valgfrit review'}</div>}
    </div>
  )
}



function StatusBadge({ label, tone }) {
  const colors = tone === 'green' ? ['#dcfce7', '#166534'] : tone === 'red' ? ['#fee2e2', '#991b1b'] : ['#fef3c7', '#92400e']
  return <span style={{ ...badgeStyle, background: colors[0], color: colors[1] }}>{label}</span>
}



function StatusCard({ label, value, color = '#1f2937' }) {
  return <div style={statusCardStyle}><div style={statusLabelStyle}>{label}</div><div style={{ ...statusValueStyle, color }}>{value}</div></div>
}



function ErrorBox({ children }) {
  return <div style={errorStyle}>{children}</div>
}



const mainStyle = { maxWidth: '1200px', margin: '0 auto', padding: '48px 24px' }
const headerStyle = { marginBottom: '40px' }
const titleStyle = { margin: 0, fontSize: '36px' }
const subtitleStyle = { marginTop: '8px', color: '#6b7280', fontSize: '18px' }
const sectionStyle = { background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: '12px', padding: '24px', marginBottom: '24px' }
const sectionTitleStyle = { marginTop: 0 }
const mutedStyle = { color: '#6b7280' }
const mutedSmallStyle = { color: '#9ca3af', fontSize: '14px' }
const gridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }
const analysisGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '14px', marginTop: '20px' }
const uploadRowStyle = { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginTop: '20px' }
const selectedFileStyle = { marginTop: '14px', color: '#4b5563' }
const buttonStyle = { border: 0, borderRadius: '8px', padding: '11px 18px', color: '#ffffff', fontWeight: 700 }
const secondaryButtonStyle = { border: '1px solid #d1d5db', borderRadius: '8px', padding: '9px 13px', background: '#ffffff', color: '#374151', fontWeight: 600, cursor: 'pointer' }
const noticeStyle = { marginTop: '24px', padding: '16px', borderRadius: '8px', background: '#f9fafb', color: '#4b5563' }
const analysisTabsStyle = { display: 'flex', gap: '8px', marginTop: '24px', paddingBottom: '10px', borderBottom: '1px solid #e5e7eb', overflowX: 'auto' }
const analysisTabStyle = { flex: '0 0 auto', border: '1px solid #d1d5db', borderRadius: '999px', padding: '9px 14px', background: '#ffffff', color: '#4b5563', fontWeight: 800, cursor: 'pointer' }
const activeAnalysisTabStyle = { borderColor: '#2563eb', background: '#eff6ff', color: '#1d4ed8', boxShadow: 'inset 0 0 0 1px #2563eb' }
const conflictAnalysisTabStyle = { borderColor: '#fecaca', color: '#b91c1c', background: '#fffafa' }
const activeConflictAnalysisTabStyle = { borderColor: '#dc2626', color: '#991b1b', background: '#fef2f2', boxShadow: 'inset 0 0 0 1px #dc2626' }
const productSectionStyle = { marginTop: '36px' }
const productSectionTitleStyle = { margin: 0, fontSize: '20px' }
const sectionHeadingRowStyle = { display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap' }
const smallActionsStyle = { display: 'flex', gap: '8px', flexWrap: 'wrap' }
const productListStyle = { display: 'grid', gap: '12px', marginTop: '16px' }
const productCardStyle = { border: '1px solid #e5e7eb', borderRadius: '10px', padding: '18px', background: '#ffffff' }
const conflictCardStyle = { ...productCardStyle, borderColor: '#fecaca', background: '#fffafa' }
const conflictMessageStyle = { marginTop: '14px', padding: '12px 14px', borderRadius: '8px', background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontWeight: 600 }
const goldenRecordMatchStyle = { marginTop: '16px', padding: '14px', borderRadius: '8px', background: '#f9fafb', border: '1px solid #e5e7eb' }
const conflictBlockedStyle = { marginTop: '16px', color: '#991b1b', fontSize: '13px', fontWeight: 700 }
const productHeaderStyle = { display: 'flex', justifyContent: 'space-between', gap: '20px', alignItems: 'flex-start' }
const selectHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', marginBottom: '14px' }
const checkboxLabelStyle = { display: 'flex', gap: '9px', alignItems: 'center', fontWeight: 700, cursor: 'pointer' }
const productCodeStyle = { fontWeight: 700, fontSize: '16px' }
const productNameStyle = { marginTop: '4px', color: '#374151' }
const eanStyle = { marginTop: '5px', color: '#9ca3af', fontSize: '13px' }
const incomingCodeStyle = { marginTop: '7px', color: '#7c3aed', fontSize: '13px' }
const badgeStyle = { padding: '5px 10px', borderRadius: '999px', fontSize: '12px', fontWeight: 700 }
const productFieldsStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginTop: '16px' }
const productFieldStyle = { background: '#f9fafb', padding: '10px 12px', borderRadius: '7px' }
const productFieldLabelStyle = { color: '#6b7280', fontSize: '12px' }
const productFieldValueStyle = { marginTop: '3px', fontWeight: 600 }
const productFieldMetaStyle = { marginTop: '4px', color: '#6b7280', fontSize: '11px' }
const selectionFooterStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '18px', marginTop: '18px', padding: '16px', background: '#f9fafb', borderRadius: '9px', flexWrap: 'wrap' }
const reviewPanelStyle = { marginTop: '16px', padding: '16px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px' }
const reviewTitleStyle = { fontWeight: 700, marginBottom: '12px' }
const reviewGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }
const reviewInputWrapperStyle = { display: 'grid', gap: '7px', alignContent: 'start' }
const reviewInputLabelStyle = { display: 'block', fontSize: '13px', color: '#374151', fontWeight: 600 }
const requiredStyle = { color: '#b45309', fontSize: '11px' }
const reviewInputStyle = { width: '100%', border: '1px solid', borderRadius: '7px', padding: '9px 10px', color: '#111827', boxSizing: 'border-box' }
const suggestionBoxStyle = { border: '1px solid', borderRadius: '7px', padding: '10px', fontSize: '13px' }
const suggestionTitleStyle = { color: '#6b7280', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }
const suggestionEvidenceStyle = { marginTop: '3px', color: '#6b7280', fontSize: '12px' }
const strongEvidenceStyle = { marginTop: '5px', color: '#15803d', fontWeight: 700, fontSize: '12px' }
const suggestionButtonStyle = { marginTop: '8px', border: '1px solid #d1d5db', borderRadius: '6px', background: '#ffffff', padding: '6px 9px', cursor: 'pointer', fontWeight: 600, fontSize: '12px' }
const noSuggestionStyle = { color: '#9ca3af', fontSize: '11px' }
const missingStyle = { marginTop: '12px', marginBottom: 0, color: '#92400e', fontSize: '13px' }
const reviewActionsStyle = { marginTop: '16px' }
const detailsStyle = { marginTop: '12px', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: '8px', background: '#f9fafb' }
const detailsSummaryStyle = { cursor: 'pointer', color: '#4b5563', fontSize: '13px', fontWeight: 700 }
const blockingStyle = { marginTop: '12px', padding: '10px 12px', borderRadius: '7px', background: '#fef2f2', color: '#b91c1c', fontSize: '13px', fontWeight: 700 }
const gateReadyStyle = { marginTop: '12px', padding: '10px 12px', borderRadius: '7px', background: '#ecfdf5', color: '#166534', fontSize: '13px', fontWeight: 700 }
const statusCardStyle = { background: '#f9fafb', borderRadius: '8px', padding: '18px' }
const statusLabelStyle = { color: '#6b7280', fontSize: '14px', marginBottom: '6px' }
const statusValueStyle = { fontSize: '24px', fontWeight: 700 }
const errorStyle = { marginTop: '16px', padding: '14px 16px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#b91c1c' }
const warningStyle = { marginTop: '14px', padding: '12px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', color: '#92400e' }
const verificationCodeStyle = { display: 'grid', gap: '4px', marginTop: '16px', padding: '14px', background: '#ecfdf5', border: '1px solid #a7f3d0', borderRadius: '8px' }
const verificationCodeValueStyle = { fontSize: '22px', color: '#166534' }
const verificationActionsStyle = { display: 'flex', justifyContent: 'space-between', gap: '14px', marginTop: '24px', flexWrap: 'wrap' }
const approvalNoticeStyle = { marginTop: '14px', color: '#6b7280', fontSize: '13px' }
const approvalSuccessStyle = { padding: '18px', background: '#ecfdf5', border: '1px solid #86efac', borderRadius: '10px', color: '#166534' }
const approvalSuccessTitleStyle = { fontSize: '22px', fontWeight: 800, marginBottom: '5px' }
const approvedMetaStyle = { marginTop: '12px', color: '#6b7280', fontSize: '13px' }
const masterdataExportStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '18px', marginTop: '20px', padding: '18px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '10px', flexWrap: 'wrap' }
const masterdataTitleStyle = { color: '#166534', fontSize: '13px', fontWeight: 800, letterSpacing: '0.08em' }
const masterdataStatusStyle = { marginTop: '4px', marginBottom: '4px', color: '#166534', fontSize: '20px', fontWeight: 800 }
const workflowStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px', marginBottom: '24px', padding: '14px', border: '1px solid #e5e7eb', borderRadius: '12px', background: '#ffffff' }
const workflowStepStyle = { display: 'flex', alignItems: 'center', gap: '10px', minHeight: '42px' }
const workflowNumberStyle = { width: '30px', height: '30px', borderRadius: '999px', display: 'grid', placeItems: 'center', flex: '0 0 auto', fontSize: '13px', fontWeight: 800 }
const workflowStepLabelStyle = { color: '#1f2937', fontSize: '13px', fontWeight: 800 }
const workflowStepHintStyle = { marginTop: '2px', color: '#9ca3af', fontSize: '11px' }
const downloadReadinessStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '18px', marginTop: '20px', padding: '16px', border: '1px dashed #9ca3af', borderRadius: '10px', background: '#f9fafb', flexWrap: 'wrap' }
const downloadReadinessTitleStyle = { marginTop: '4px', marginBottom: '4px', color: '#374151', fontSize: '17px', fontWeight: 800 }
const disabledDownloadButtonStyle = { ...buttonStyle, background: '#d1d5db', color: '#6b7280', cursor: 'not-allowed' }
const coreSkuGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px', marginTop: '16px', padding: '12px', border: '1px solid #dbeafe', borderRadius: '9px', background: '#eff6ff' }
const derivedPreviewStyle = { marginTop: '12px', padding: '12px', border: '1px solid #d1fae5', borderRadius: '9px', background: '#f0fdf4' }
const derivedPreviewTitleStyle = { color: '#166534', fontSize: '12px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }
const derivedGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '10px', marginTop: '8px' }
const evidencePanelStyle = { paddingTop: '2px' }
const evidenceSourceStyle = { marginTop: '12px', padding: '10px 12px', borderRadius: '7px', background: '#eef2ff', color: '#3730a3', fontSize: '13px' }
const optionalWarningDetailsStyle = { marginTop: '12px', border: '1px solid #fde68a', borderRadius: '8px', background: '#fffbeb' }
const optionalWarningSummaryStyle = { padding: '10px 12px', cursor: 'pointer', color: '#166534', fontSize: '13px', fontWeight: 800 }
const optionalWarningBodyStyle = { padding: '0 12px 12px', color: '#92400e', fontSize: '13px' }
const reviewEditorDetailsStyle = { marginTop: '12px', border: '1px solid #d1d5db', borderRadius: '9px', background: '#ffffff' }
const reviewEditorSummaryStyle = { padding: '12px 14px', cursor: 'pointer', color: '#374151', fontSize: '13px', fontWeight: 800 }
const reviewEditorBodyStyle = { display: 'grid', gap: '14px', padding: '0 14px 14px' }
const savedSummaryStyle = { marginTop: '14px', padding: '14px', border: '1px solid #86efac', borderRadius: '9px', background: '#f0fdf4', color: '#166534' }
const savedSummaryTitleStyle = { fontSize: '16px', fontWeight: 800 }
const savedValuesGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '8px', marginTop: '10px' }
const savedSummaryMetaStyle = { marginTop: '9px', color: '#4b5563', fontSize: '13px' }
const savedNextStepStyle = { marginTop: '10px', fontWeight: 800 }
const blockingInlineStyle = { marginTop: '9px', color: '#b91c1c', fontSize: '13px', fontWeight: 800 }
const reviewFirstPanelStyle = { marginTop: '16px', padding: '16px', border: '1px solid #bbf7d0', borderRadius: '10px', background: '#f0fdf4' }
const reviewFirstHeaderStyle = { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }
const readyForSkuStyle = { color: '#166534', fontSize: '19px', fontWeight: 900 }
const automaticTitleStyle = { marginTop: '3px', color: '#4b5563', fontSize: '13px', fontWeight: 700 }
const automaticGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '8px 18px', marginTop: '14px' }
const automaticFieldStyle = { display: 'flex', gap: '8px', alignItems: 'flex-start', color: '#1f2937', fontSize: '14px' }
const automaticCheckStyle = { fontSize: '15px', fontWeight: 900, lineHeight: 1.4 }
const automaticFieldLabelStyle = { color: '#6b7280' }
const textSourceStyle = { display: 'block', marginTop: '2px', color: '#6b7280', fontSize: '11px' }
const textReviewStyle = { display: 'block', marginTop: '2px', color: '#b45309', fontSize: '11px', fontWeight: 700 }
const overrideBadgeStyle = { display: 'inline-block', marginLeft: '8px', padding: '2px 7px', borderRadius: '999px', background: '#fef3c7', color: '#92400e', fontSize: '10px', fontWeight: 800 }
const evidenceInlineStyle = { marginTop: '14px', paddingTop: '12px', borderTop: '1px solid #bbf7d0', color: '#166534', fontSize: '13px' }
const optionalMissingStyle = { marginTop: '8px', color: '#92400e', fontSize: '13px' }
const activeOverridesStyle = { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginTop: '12px', padding: '10px 12px', borderRadius: '8px', background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontSize: '13px' }
const resetOverrideButtonStyle = { border: '1px solid #f59e0b', borderRadius: '7px', padding: '6px 9px', background: '#ffffff', color: '#92400e', cursor: 'pointer', fontWeight: 700, fontSize: '12px' }
const overrideActionStyle = { marginTop: '12px', border: '1px solid #d1d5db', borderRadius: '8px', padding: '9px 13px', background: '#ffffff', color: '#374151', cursor: 'pointer', fontWeight: 700 }
const overridePanelStyle = { display: 'grid', gap: '12px', marginTop: '12px', padding: '16px', border: '1px solid #f59e0b', borderRadius: '10px', background: '#fffbeb' }
const overridePanelTitleStyle = { color: '#92400e', fontSize: '16px', fontWeight: 900 }
const overrideFieldStyle = { display: 'grid', gap: '7px', padding: '12px', border: '1px solid #fde68a', borderRadius: '8px', background: '#ffffff' }
const overrideFieldHeaderStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }
const overrideFieldLabelStyle = { color: '#1f2937', fontWeight: 800 }
const automaticValueStyle = { color: '#6b7280', fontSize: '12px' }
const overrideControlStyle = { marginTop: '2px' }
const enableOverrideButtonStyle = { border: '1px solid #d97706', borderRadius: '7px', padding: '7px 10px', background: '#ffffff', color: '#92400e', cursor: 'pointer', fontWeight: 800, fontSize: '12px' }
const cancelOverrideButtonStyle = { ...enableOverrideButtonStyle, borderColor: '#d1d5db', color: '#4b5563' }
const overrideOptionsErrorStyle = { padding: '8px 10px', borderRadius: '7px', background: '#fef2f2', color: '#991b1b', fontSize: '12px', fontWeight: 700 }
const reviewSelectStyle = { width: '100%', border: '1px solid #d1d5db', borderRadius: '7px', padding: '9px 10px', background: '#ffffff', color: '#111827', boxSizing: 'border-box' }
const reviewTextareaStyle = { width: '100%', marginTop: '6px', border: '1px solid #d1d5db', borderRadius: '7px', padding: '9px 10px', color: '#111827', boxSizing: 'border-box', resize: 'vertical' }



const familyCandidatesStyle = { display: 'grid', gap: '8px', marginTop: '14px', padding: '12px', border: '1px solid #bfdbfe', borderRadius: '8px', background: '#eff6ff' }
const familyCandidateButtonStyle = { display: 'grid', gap: '4px', width: '100%', padding: '10px', textAlign: 'left', color: '#1e3a8a', background: '#ffffff', border: '1px solid #93c5fd', borderRadius: '7px', cursor: 'pointer' }

export default App

const lifecycleSummaryStyle = { display: 'grid', gap: '8px', marginTop: '16px', padding: '14px', borderRadius: '9px', background: '#eff6ff', border: '1px solid #bfdbfe', color: '#1e3a8a', fontSize: '13px' }
const lifecycleCountsStyle = { display: 'flex', gap: '12px', flexWrap: 'wrap', color: '#1f2937' }
const lifecycleNextStepStyle = { display: 'grid', gap: '4px', marginTop: '14px', marginBottom: '14px', padding: '12px', borderRadius: '8px', background: '#f5f3ff', border: '1px solid #ddd6fe', color: '#5b21b6', fontSize: '13px' }
