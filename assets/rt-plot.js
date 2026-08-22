/* =====================================================================
   research-tools 共通プロットヘルパ（軸の刻み幅）

   注意: 4 ツールの「nice tick」は 2 系統あり、数値挙動が違う。
   まとめずに 2 本のまま置いてある。

   (A) rtNiceStep … squid-plotter / xrd-plotter の calcStep が使う仮数丸め。
       しきい値は 1.5 / 3.5 / 7.5。両ファイルでこの部分だけは完全一致だが、
       範囲を割る数（squid = ÷6、xrd = ÷8）と入力ガード（xrd だけ isFinite を
       見る）は違うので、そこは各ページの calcStep に残してある。

   (B) rtNiceNum … cfms-plotter / dmm-viewer の niceNum。
       しきい値は round=true で 1.5 / 3 / 7、round=false で 1 / 2 / 5。
       両ファイルで数値挙動は完全に同じ（書き方が if/else と三項で違うだけ）。

   (A) と (B) はしきい値が違うので互いに置き換えられない。
   ===================================================================== */

/* (A) raw（＝すでに刻み数で割った後の値）を 1/2/5/10 × 10^n に丸める */
function rtNiceStep(raw){
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw/mag;
  if(norm<=1.5) return mag;
  if(norm<=3.5) return 2*mag;
  if(norm<=7.5) return 5*mag;
  return 10*mag;
}

/* (B) range を 1/2/5/10 × 10^n に丸める。round=false は「切り上げ寄り」。 */
function rtNiceNum(range, round){
  if(range<=0) return 1;
  const exp = Math.floor(Math.log10(range));
  const frac = range/Math.pow(10, exp);
  let nice;
  if(round){ nice = frac<1.5?1:frac<3?2:frac<7?5:10; }
  else{ nice = frac<=1?1:frac<=2?2:frac<=5?5:10; }
  return nice*Math.pow(10, exp);
}
