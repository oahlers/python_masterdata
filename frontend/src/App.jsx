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
  const [approval, setApproval] = useState(null)



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
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch('/api/analyze', { method: 'POST', body: formData })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Filen kunne ikke analyseres.')
      setAnalysis(data)
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



  if (verification) {
    return (
      <main style={mainStyle}>
        <header style={headerStyle}>
          <h1 style={titleStyle}>Sæther Masterdata Automation</h1>
          <p style={subtitleStyle}>Verificering før godkendelse og M3</p>
        </header>
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
          <div style={noticeStyle}>Analysen har ikke skrevet noget til M3.</div>



          <ReadySelectionSection
            products={analysis.ready_products || []}
            selectedKeys={selectedKeys}
            onToggle={toggleProduct}
            onSelectAll={selectAllReady}
            onClear={() => setSelectedKeys([])}
            onPrepare={prepareSelected}
            preparing={preparing}
            error={prepareError}
          />



          <ConflictSection
            products={analysis.conflict_products || []}
          />



          <ProductSection
            title={`Kræver review (${analysis.review})`}
            products={analysis.review_products || []}
            analysis={analysis}
            setAnalysis={setAnalysis}
          />
        </section>
      )}
    </main>
  )
}



function ReadySelectionSection({ products, selectedKeys, onToggle, onSelectAll, onClear, onPrepare, preparing, error }) {
  if (!products.length) return null
  return (
    <div style={productSectionStyle}>
      <div style={sectionHeadingRowStyle}>
        <h3 style={productSectionTitleStyle}>Klar til Sæther Code ({products.length})</h3>
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
          onClick={onPrepare}
          disabled={preparing || selectedKeys.length === 0}
          style={{ ...buttonStyle, background: preparing || selectedKeys.length === 0 ? '#9ca3af' : '#111827', cursor: preparing ? 'wait' : 'pointer' }}
        >
          {preparing ? 'Forbereder...' : 'Fortsæt til verificering'}
        </button>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
    </div>
  )
}



function VerificationView({ verification, approval, onApproval, onBack }) {
  const [approving, setApproving] = useState(false)
  const [approvalError, setApprovalError] = useState(null)



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



  const canApprove = verification.can_continue && verification.blocked_count === 0 && verification.prepared_count > 0



  return (
    <section style={sectionStyle}>
      <h2 style={sectionTitleStyle}>Verificér produkter</h2>
      <p style={mutedStyle}>Kontrollér alle værdier og reserverede Sæther Codes. Der er endnu ikke godkendt eller sendt noget til M3.</p>
      <div style={analysisGridStyle}>
        <StatusCard label="Valgt" value={verification.requested_count} />
        <StatusCard label="Forberedt" value={verification.prepared_count} color="#15803d" />
        <StatusCard label="Blokeret" value={verification.blocked_count} color={verification.blocked_count ? '#dc2626' : '#15803d'} />
      </div>
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
              <ProductField label="MMSTAT" value={item.mmstat} />
              <ProductField label="MMITTY" value={item.item_type} />
              <ProductField label="MMBUAR" value={item.brand_code} />
              <ProductField label="MMITGR" value={item.item_group} />
              <ProductField label="MMITCL" value={item.item_class} />
              <ProductField label="Product Line" value={item.product_line} />
            </div>
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




function ProductSection({ title, products, analysis, setAnalysis }) {
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
            <ReviewEditor product={product} analysis={analysis} setAnalysis={setAnalysis} />
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



function ReadyFields({ product }) {
  return (
    <div style={productFieldsStyle}>
      <ProductField label="BMS Type" value={product.product_type} />
      <ProductField label="MMSTAT" value={product.mmstat} />
      <ProductField label="MMITTY" value={product.item_type} />
      <ProductField label="MMBUAR" value={product.brand_code} />
      <ProductField label="MMITGR" value={product.item_group} />
      <ProductField label="MMITCL" value={product.item_class} />
      <ProductField label="Product Line" value={product.product_line} />
      <ProductField label="Sæther Code" value={product.item_number} warning={!product.item_number} />
    </div>
  )
}



function ReviewEditor({ product, analysis, setAnalysis }) {
  const [itemType, setItemType] = useState(product.item_type || '')
  const [itemGroup, setItemGroup] = useState(product.item_group || '')
  const [itemClass, setItemClass] = useState(product.item_class || '')
  const [productLine, setProductLine] = useState(product.product_line || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const missing = (product.needs_review || []).filter((field) => field !== 'item_number')
  const isMissing = (fieldName) => missing.includes(fieldName)
  const getSuggestion = (fieldName) => (product.suggestions || []).find((item) => item.field_name === fieldName)
  const useSuggestion = (fieldName, setter) => {
    const suggestion = getSuggestion(fieldName)
    if (suggestion) setter(suggestion.suggested_value)
  }



  async function saveReview() {
    if (!analysis.analysis_id) return setError('Analysis ID mangler. Upload filen igen.')
    const productKey = product.ean || product.product_code
    if (!productKey) return setError('Produktet mangler både EAN og produktkode.')
    const body = {
      item_type: isMissing('item_type') ? itemType.trim() || null : null,
      item_group: isMissing('item_group') ? itemGroup.trim() || null : null,
      item_class: isMissing('item_class') ? itemClass.trim() || null : null,
      product_line: isMissing('product_line') ? productLine.trim() || null : null,
    }
    if (!Object.values(body).some(Boolean)) return setError('Udfyld mindst ét manglende review-felt.')
    setSaving(true)
    setError(null)
    try {
      const response = await fetch(
        `/api/reviews/${encodeURIComponent(analysis.analysis_id)}/${encodeURIComponent(productKey)}`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      )
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Review kunne ikke gemmes.')
      setAnalysis(data.analysis)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }



  return (
    <>
      <div style={productFieldsStyle}>
        <ProductField label="BMS Type" value={product.product_type} />
        <ProductField label="MMSTAT" value={product.mmstat} />
        <ProductField label="MMBUAR" value={product.brand_code} />
        <ProductField label="Family Match" value={product.family_match} />
      </div>
      <div style={reviewPanelStyle}>
        <div style={reviewTitleStyle}>Review felter</div>
        <div style={reviewGridStyle}>
          <ReviewInput label="MMITTY" value={itemType} onChange={setItemType} required={isMissing('item_type')} disabled={!isMissing('item_type')} suggestion={getSuggestion('item_type')} onUseSuggestion={() => useSuggestion('item_type', setItemType)} />
          <ReviewInput label="MMITGR" value={itemGroup} onChange={setItemGroup} required={isMissing('item_group')} disabled={!isMissing('item_group')} suggestion={getSuggestion('item_group')} onUseSuggestion={() => useSuggestion('item_group', setItemGroup)} />
          <ReviewInput label="MMITCL" value={itemClass} onChange={setItemClass} required={isMissing('item_class')} disabled={!isMissing('item_class')} suggestion={getSuggestion('item_class')} onUseSuggestion={() => useSuggestion('item_class', setItemClass)} />
          <ReviewInput label="Product Line" value={productLine} onChange={setProductLine} required={isMissing('product_line')} disabled={!isMissing('product_line')} suggestion={getSuggestion('product_line')} onUseSuggestion={() => useSuggestion('product_line', setProductLine)} />
        </div>
        {missing.length > 0 && <p style={missingStyle}>Mangler: {missing.join(', ')}</p>}
        {error && <ErrorBox>{error}</ErrorBox>}
        <div style={reviewActionsStyle}>
          <button type="button" onClick={saveReview} disabled={saving} style={{ ...buttonStyle, background: saving ? '#9ca3af' : '#111827', cursor: saving ? 'wait' : 'pointer' }}>
            {saving ? 'Gemmer...' : 'Gem review'}
          </button>
        </div>
      </div>
    </>
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



function ProductField({ label, value, warning = false }) {
  const missing = value === null || value === undefined || value === ''
  return (
    <div style={productFieldStyle}>
      <div style={productFieldLabelStyle}>{label}</div>
      <div style={{ ...productFieldValueStyle, color: warning || missing ? '#b45309' : '#1f2937' }}>{missing ? 'Mangler' : String(value)}</div>
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



export default App
