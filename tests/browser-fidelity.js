/* Evaluate on the running app; uses real API responses, table rendering and CSV.
   Restart the server after core.py changes before the default full check.
   For a frontend-only check against an older server, set
   window.querycraftFidelityBinaryOnly = true before evaluating this expression.
   Binary cells consistently use 0x-prefixed hexadecimal in both table and CSV.
*/
(async () => {
  const checks = [];
  const $ = (id) => document.getElementById(id);
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const until = async (condition) => {
    for (let n = 0; n < 150; n++) {
      if (condition()) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    throw new Error('Timed out waiting for UI state');
  };
  const run = async (sql) => {
    $('sql').value = sql;
    $('sql').dispatchEvent(new Event('input', {bubbles:true}));
    $('run').click();
    await until(() => !$('run').disabled);
    assert($('execute-error').hidden, $('execute-error').textContent);
    return Array.from($('results-body').querySelectorAll('td'), td => td.textContent);
  };
  const api = async (sql) => {
    const response = await fetch('/api/execute', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({sql})
    });
    assert(response.ok, 'API execution failed');
    return (await response.json()).rows[0];
  };
  const exportCSV = async () => {
    let captured;
    const oldURL = URL.createObjectURL;
    const oldClick = HTMLAnchorElement.prototype.click;
    try {
      URL.createObjectURL = (blob) => { captured = blob; return oldURL(blob); };
      HTMLAnchorElement.prototype.click = function () { if (!this.download) oldClick.call(this); };
      $('download').click();
      assert(captured instanceof Blob, 'CSV blob missing');
      return await captured.text();
    } finally {
      URL.createObjectURL = oldURL;
      HTMLAnchorElement.prototype.click = oldClick;
    }
  };
  await until(() => $('connection').textContent === 'Connected · SQLite');
  const binarySQL = "SELECT x'00ff' AS binary, x'' AS empty_binary, NULL AS missing, 1.25 AS finite, ' =1+2' AS formula, 'a\"b' AS quoted";
  const binary = await api(binarySQL);
  assert(JSON.stringify(binary.slice(0, 3)) === '[{"hex":"00ff"},{"hex":""},null]', 'Binary API contract changed');
  checks.push('binary API hex objects unchanged');
  const binaryCells = await run(binarySQL);
  assert(JSON.stringify(binaryCells) === JSON.stringify(['0x00ff', '0x', 'NULL', '1.25', ' =1+2', 'a"b']), 'Binary/null table fidelity: ' + JSON.stringify(binaryCells));
  checks.push('binary table uses 0x prefix; null stays NULL');
  const binaryCSV = await exportCSV();
  assert(binaryCSV === '"binary","empty_binary","missing","finite","formula","quoted"\r\n"0x00ff","0x","","1.25","\' =1+2","a""b"\r\n', 'Binary/null CSV fidelity: ' + JSON.stringify(binaryCSV));
  checks.push('binary CSV uses 0x prefix; null stays empty; formula/quote safety unchanged');
  assert(csvCell(false) === '"false"' && csvCell(0) === '"0"' && csvCell(undefined) === '""', 'Scalar CSV behavior changed');
  checks.push('scalar CSV behavior unchanged');
  if (!window.querycraftFidelityBinaryOnly) {
    const integerSQL = 'SELECT 9007199254740993 AS positive, -9007199254740993 AS negative, 9007199254740992 AS above_safe, -9007199254740992 AS below_safe, 9007199254740991 AS safe_positive, -9007199254740991 AS safe_negative, 9223372036854775807 AS maximum, -9223372036854775808 AS minimum';
    const expected = ['9007199254740993', '-9007199254740993', '9007199254740992', '-9007199254740992', 9007199254740991, -9007199254740991, '9223372036854775807', '-9223372036854775808'];
    assert(JSON.stringify(await api(integerSQL)) === JSON.stringify(expected), 'Integer API lost precision or safe numeric types');
    checks.push('integer API exact decimal strings outside safe range, numbers inside');
    assert(JSON.stringify(await run(integerSQL)) === JSON.stringify(expected.map(String)), 'Integer table lost precision');
    checks.push('exact integer table values including SQLite min/max');
    const integerCSV = await exportCSV();
    const expectedRow = expected.map(value => '"' + (String(value).startsWith('-') ? "'" : '') + value + '"').join(',') + '\r\n';
    assert(integerCSV.endsWith('\r\n' + expectedRow), 'Integer CSV lost precision or formula protection');
    checks.push('exact integer CSV values with existing negative-value safety');
  }
  return {passed:true, checks, binaryOnly:Boolean(window.querycraftFidelityBinaryOnly)};
})()
