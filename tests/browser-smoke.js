/* Run this async expression in DevTools on the bundled demo at 127.0.0.1:5055.
   It exercises the actual HTTP backend. No model calls or database writes.
   A successful result is {passed:true, checks:[...]}.
*/
(async () => {
  const checks = [];
  const $ = (id) => document.getElementById(id);
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const until = async (condition) => {
    for (let n = 0; n < 120; n++) {
      if (condition()) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    throw new Error('Timed out waiting for UI state');
  };
  const edit = (id, value) => { $(id).value = value; $(id).dispatchEvent(new Event('input', {bubbles:true})); };
  const run = async (sql) => {
    edit('sql', sql);
    $('run').click();
    await until(() => !$('run').disabled);
  };
  await until(() => $('connection').textContent === 'Connected · SQLite');
  assert($('database-name').textContent === 'Demo store', 'Use the bundled demo, not a custom database');
  $('reset').click();
  edit('question', 'What is the total revenue?');
  $('generate').click();
  await until(() => !$('generate').disabled);
  assert($('sql').value.includes('SELECT'), 'Generated SQL missing');
  assert($('results-table-wrap').hidden && $('download').disabled, 'Generation executed SQL unexpectedly');
  checks.push('generate without execution');
  $('run').click();
  await until(() => !$('run').disabled);
  assert($('results-body').textContent.includes('110'), 'Actual demo revenue mismatch');
  checks.push('real SQLite result');
  edit('sql', 'SELECT name FROM customers');
  assert($('download').disabled && $('results-table-wrap').hidden, 'Stale results not cleared');
  checks.push('stale result invalidation');
  await run('DROP TABLE customers');
  assert(!$('execute-error').hidden && $('download').disabled, 'Write query not rejected');
  checks.push('write rejection');
  await run('SELECT name FROM customers WHERE 0');
  assert(!$('results-empty').hidden && $('results-meta').textContent.startsWith('0 rows'), 'Empty result state wrong');
  checks.push('empty results');
  await run('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<205) SELECT x FROM n');
  assert($('results-body').children.length === 200 && !$('truncated').hidden, 'Row cap not visible');
  checks.push('200-row truncation');
  await run("SELECT '<img src=x onerror=alert(1)>' AS sample, ' =1+2' AS formula, 'a\"b' AS quoted");
  assert(!$('results-body').querySelector('img'), 'Database content treated as HTML');
  assert($('results-body').textContent.includes('<img'), 'Raw text was not preserved');
  checks.push('text-only result rendering');
  let captured;
  const oldURL = URL.createObjectURL;
  const oldClick = HTMLAnchorElement.prototype.click;
  try {
    URL.createObjectURL = (blob) => { captured = blob; return oldURL(blob); };
    HTMLAnchorElement.prototype.click = function () { if (!this.download) oldClick.call(this); };
    $('download').click();
    assert(captured instanceof Blob, 'CSV blob missing');
    const csv = await captured.text();
    assert(csv.includes("\"' =1+2\""), 'CSV formula not neutralized');
    assert(csv.includes('a""b'), 'CSV quotes not escaped');
    checks.push('CSV export from real results');
  } finally {
    URL.createObjectURL = oldURL;
    HTMLAnchorElement.prototype.click = oldClick;
  }
  await run('SELECT 1e999 AS overflow');
  assert($('results-body').textContent.includes('Infinity'), 'Numeric overflow response not valid JSON');
  checks.push('browser-safe overflow response');
  $('reset').click();
  assert(!$('question').value && !$('sql').value && $('run').disabled && $('download').disabled, 'Reset incomplete');
  checks.push('reset');
  assert(document.documentElement.scrollWidth <= innerWidth, 'Horizontal page overflow');
  checks.push('viewport fit');
  return {passed:true, checks};
})()
