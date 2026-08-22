/* =====================================================================
   research-tools 共通ファイル読み込み
   （複数エンコーディング試行 → バイナリフォールバック）

   squid-plotter と xrd-plotter が同じ手順を別々に持っていたのを共通化した。
   エンコーディングの並び順・フォールバックの条件・alert 文面は元のまま。
   ===================================================================== */

const RT_ENCODINGS = ['shift_jis','utf-8','euc-jp','iso-8859-1'];

/* 装置が吐く非テキスト混じりのバイト列を、タブ・改行・ASCII 可読文字だけに
   落として復元する（それ以外のバイトは空白に潰す）。*/
function rtBinaryToText(buffer){
  const arr = new Uint8Array(buffer);
  let text = '';
  for(let i=0;i<arr.length;i++){
    const b = arr[i];
    if(b===0x09) text+='\t';
    else if(b===0x0A) text+='\n';
    else if(b===0x0D) continue;
    else if(b>=0x20&&b<=0x7E) text+=String.fromCharCode(b);
    else text+=' ';
  }
  return text;
}

/* file を encodings の順に読み、onText が true を返した時点で終了する。
   全エンコーディングで false ならバイナリとして読み直し、それも false なら
   「データを読み取れませんでした」と出す。

   onText(text, isBinaryFallback) -> boolean  … 採用できたら true を返すこと。*/
function rtReadFileMultiEncoding(file, onText, encodings){
  const encs = encodings || RT_ENCODINGS;
  let tryIdx = 0;
  function tryRead(){
    const reader = new FileReader();
    reader.onload = e => {
      if(onText(e.target.result, false)) return;
      tryIdx++;
      if(tryIdx<encs.length){ tryRead(); return; }
      // 全エンコーディングで駄目 → バイナリとして読み直し
      const binReader = new FileReader();
      binReader.onload = ev => {
        if(!onText(rtBinaryToText(ev.target.result), true)){
          alert('データを読み取れませんでした: '+file.name);
        }
      };
      binReader.readAsArrayBuffer(file);
    };
    reader.onerror = () => {
      tryIdx++;
      if(tryIdx<encs.length) tryRead();
      else alert('読み込み失敗: '+file.name);
    };
    reader.readAsText(file, encs[tryIdx]);
  }
  tryRead();
}
