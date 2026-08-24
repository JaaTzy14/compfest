'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';

const MapPicker = dynamic(() => import('../components/MapPicker'), {
  ssr: false,
  loading: () => <div className="w-full h-[250px] bg-gray-100 animate-pulse flex items-center justify-center text-gray-400 text-sm font-medium">Loading Map...</div>
});

const CATALOG = [
  { id: 8, name: "Cabe Merah Keriting", icon: "🌶️" },
  { id: 10, name: "Cabe Rawit Merah", icon: "🌶️" },
  { id: 12, name: "Bawang Merah", icon: "🧅" },
  { id: 17, name: "Telur Ayam Ras", icon: "🥚" },
  { id: 22, name: "Tomat Buah", icon: "🍅" },
];

type PlanLine = {
  commodity: string;
  market_name: string;
  target_date: string;
  qty_kg: number;
  expected_price_per_kg?: number;
};

type PlanResult = {
  lines?: PlanLine[];
  purchase_cost?: number;
  transport_cost?: number;
  total_expected_cost?: number;
  worst_case_total_cost?: number;
  estimated_saving_vs_baseline?: number;
  estimated_saving_pct?: number;
  alternative_plans?: {
    cheapest?: PlanResult;
    low_risk?: PlanResult;
  };
};

export default function Home() {
  // Mengosongkan form di awal:
  const [location, setLocation] = useState<[number | string, number | string]>(['', '']);
  const [deadline, setDeadline] = useState('');
  const [strategy, setStrategy] = useState('Balanced');
  
  const [planResult, setPlanResult] = useState<PlanResult | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState<string | null>(null);

  const [items, setItems] = useState<Array<{ id: number; name: string; qty: number; icon: string }>>([]);

  const handleAddItem = () => {
    setItems([...items, { id: CATALOG[0].id, name: CATALOG[0].name, qty: 1, icon: CATALOG[0].icon }]);
  };

  const handleRemoveItem = (indexToRemove: number) => {
    setItems(items.filter((_, index) => index !== indexToRemove));
  };

  const handleQtyChange = (index: number, newQty: string) => {
    const val = Math.max(1, parseInt(newQty) || 1);
    const newItems = [...items];
    newItems[index].qty = val;
    setItems(newItems);
  };

  const handleItemChange = (index: number, newIdStr: string) => {
    const newId = parseInt(newIdStr);
    const selected = CATALOG.find(c => c.id === newId);
    if (selected) {
      const newItems = [...items];
      newItems[index] = { ...newItems[index], id: selected.id, name: selected.name, icon: selected.icon };
      setItems(newItems);
    }
  };

  const handleFindPlan = async (e: React.FormEvent) => {
    e.preventDefault();
    
    let riskAversionValue = 0.5;
    if (strategy === 'Cheapest') riskAversionValue = 0.0;
    if (strategy === 'Low Risk') riskAversionValue = 1.0;

    const mappedCommodities: Record<number, number> = {};
    items.forEach(item => {
        mappedCommodities[item.id] = item.qty;
    });

    const payload = {
      allow_split: false,
      commodities: mappedCommodities,
      deadline: deadline,
      location: [Number(location[0]) || 0, Number(location[1]) || 0],
      max_markets: 2,
      max_trips: 2,
      risk_aversion: riskAversionValue
    };

    try {
      const response = await fetch('http://localhost:8000/api/v1/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Respons dari backend:", data);
        setPlanResult(data as PlanResult);
        setShowResult(true);
      } else {
        const errorData = await response.json();
        console.error("Gagal dari backend:", errorData);
      }
    } catch (error) {
      console.error("Terjadi kesalahan jaringan:", error);
    }
  };

  const handleRefreshData = async () => {
    setIsRefreshing(true);
    setRefreshStatus(null);

    try {
      const response = await fetch('http://localhost:8000/api/v1/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      const data = await response.json();

      if (response.ok) {
        setRefreshStatus(
          `Forecast updated: ${data.forecast_start_date} - ${data.forecast_end_date}`
        );
      } else {
        setRefreshStatus(data.detail || 'Refresh failed');
      }
    } catch (error) {
      console.error("Terjadi kesalahan refresh:", error);
      setRefreshStatus('Network error while refreshing');
    } finally {
      setIsRefreshing(false);
    }
  };

  // Menentukan data plan aktif berdasarkan strategi yang dipilih user
  let activePlan = planResult;
  if (planResult) {
    if (strategy === 'Cheapest' && planResult.alternative_plans?.cheapest) {
      activePlan = planResult.alternative_plans.cheapest;
    } else if (strategy === 'Low Risk' && planResult.alternative_plans?.low_risk) {
      activePlan = planResult.alternative_plans.low_risk;
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans">
      {/* HEADER */}
      <header className="bg-white border-b border-gray-200 shadow-sm px-8 py-4 flex items-center justify-between sticky top-0 z-20">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900 flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600 text-white text-sm font-bold">P</span>
            ProcureAI
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">Smarter Food Procurement</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-red-50 text-base">🌶️</span>
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-amber-50 text-base">🧅</span>
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-orange-50 text-base">🧺</span>
          </div>
          <div className="text-right">
            <button
              type="button"
              onClick={handleRefreshData}
              disabled={isRefreshing}
              className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              {isRefreshing ? 'Refreshing...' : 'Refresh Data'}
            </button>
            {refreshStatus && (
              <p className="mt-1.5 text-xs text-gray-500 max-w-xs text-right">{refreshStatus}</p>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* KOLOM KIRI: YOUR PROCUREMENT */}
        <section className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-blue-50 text-sm">📋</span>
            <h2 className="text-base font-semibold text-gray-800">Your Procurement</h2>
          </div>

          <form onSubmit={handleFindPlan} className="p-6 space-y-6">
            {/* Location */}
            <div>
              <label className="block mb-1.5 text-sm font-medium text-gray-700">Location Origin</label>
              <div className="mb-2 text-xs text-gray-500 flex justify-between items-center">
                <span>Click on the map to set your location coordinates.</span>
                {typeof location[0] === 'number' && typeof location[1] === 'number' && !isNaN(location[0]) && (
                  <span className="font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                    {location[0].toFixed(5)}, {location[1].toFixed(5)}
                  </span>
                )}
              </div>
              <div className="border border-gray-200 rounded-lg overflow-hidden relative z-0">
                <MapPicker location={location} onChange={(loc) => setLocation(loc)} />
              </div>
            </div>

            {/* Shopping List */}
            <div>
              <label className="block mb-1.5 text-sm font-medium text-gray-700">Shopping List</label>
              <div className="space-y-2 mb-3">
                {items.map((item, index) => (
                  <div key={index} className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-md bg-white border border-gray-200 text-base shrink-0">
                      {item.icon}
                    </span>
                    <select
                      value={item.id}
                      onChange={(e) => handleItemChange(index, e.target.value)}
                      className="flex-1 bg-transparent text-sm font-medium text-gray-800 focus:outline-none cursor-pointer"
                    >
                      {CATALOG.map((cat) => (
                        <option key={cat.id} value={cat.id}>{cat.name}</option>
                      ))}
                    </select>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <input
                        type="number"
                        min="1"
                        value={item.qty}
                        onChange={(e) => handleQtyChange(index, e.target.value)}
                        className="w-14 text-center bg-white border border-gray-200 rounded-md py-1 text-sm font-semibold text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <span className="text-xs text-gray-500 font-medium">kg</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveItem(index)}
                        className="ml-1 w-6 h-6 inline-flex items-center justify-center text-red-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors text-xs font-bold"
                        title="Remove Item"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={handleAddItem}
                className="inline-flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg px-3 py-1.5 transition-colors"
              >
                <span className="text-base">🧺</span>
                Add Item
              </button>
            </div>

            {/* Deadline */}
            <div>
              <label className="block mb-1.5 text-sm font-medium text-gray-700">Deadline</label>
              <input
                type="date"
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-lg text-gray-900 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            {/* Strategy */}
            <div>
              <label className="block mb-1.5 text-sm font-medium text-gray-700">Procurement Strategy</label>
              <div className="space-y-2">
                {[
                  { name: 'Cheapest', icon: '💰', desc: 'Minimize cost, higher variance' },
                  { name: 'Balanced', icon: '⚖️', desc: 'Balance cost and reliability' },
                  { name: 'Low Risk', icon: '🛡️', desc: 'Prioritize reliability, stable pricing' },
                ].map((opt) => (
                  <label
                    key={opt.name}
                    className={`flex items-center gap-3 cursor-pointer p-3 rounded-lg border transition-all ${
                      strategy === opt.name
                        ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="strategy"
                      value={opt.name}
                      checked={strategy === opt.name}
                      onChange={(e) => setStrategy(e.target.value)}
                      className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                    />
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-md bg-white border border-gray-200 text-base">
                      {opt.icon}
                    </span>
                    <div>
                      <p className={`text-sm font-semibold ${strategy === opt.name ? 'text-blue-700' : 'text-gray-800'}`}>{opt.name}</p>
                      <p className="text-xs text-gray-500">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Submit */}
            <div className="pt-2">
              <button
                type="submit"
                className="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold py-3 px-6 rounded-lg text-sm transition-colors shadow-sm flex items-center justify-center gap-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" /></svg>
                Find Best Plan
              </button>
            </div>
          </form>
        </section>

        {/* KOLOM KANAN: RECOMMENDED PLAN */}
        <section className={`bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden transition-all duration-700 ${showResult ? 'opacity-100' : 'opacity-40'}`}>
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-amber-50 text-sm">🌟</span>
            <h2 className="text-base font-semibold text-gray-800">
              Recommended Plan
              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">{strategy}</span>
            </h2>
          </div>

          <div className="p-6 space-y-6">
            {/* Best market */}
            <div className="flex items-center gap-4 pb-5 border-b border-gray-100">
              <span className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-amber-50 border border-amber-100 text-4xl shrink-0">🏘️</span>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Best Option Market</p>
                <p className="text-xl font-bold text-gray-900">
                  {activePlan?.lines && activePlan.lines.length > 0 ? activePlan.lines[0].market_name : "Select items & click Find Best Plan"}
                </p>
              </div>
            </div>

            {/* Plan lines */}
            {activePlan?.lines && activePlan.lines.length > 0 && (
              <div className="space-y-2">
                {activePlan.lines.map((line: PlanLine, idx: number) => (
                  <div key={idx} className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-white border border-gray-200 text-sm">🛒</span>
                      <div>
                        <p className="text-sm font-semibold text-gray-800">{line.commodity}</p>
                        <p className="text-xs text-gray-500">{line.target_date} · Rp {line.expected_price_per_kg?.toLocaleString('id-ID')}/kg</p>
                      </div>
                    </div>
                    <span className="text-sm font-bold text-gray-700 bg-white border border-gray-200 rounded-md px-2.5 py-1">{line.qty_kg} kg</span>
                  </div>
                ))}
              </div>
            )}

            {/* Cost breakdown */}
            <div className="space-y-2 pt-2">
              <div className="flex justify-between items-center py-2 border-b border-dashed border-gray-200">
                <span className="text-sm text-gray-600">Expected item cost</span>
                <span className="text-sm font-semibold text-gray-800">Rp {activePlan?.purchase_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-dashed border-gray-200">
                <span className="text-sm text-gray-600">Transport</span>
                <span className="text-sm font-semibold text-gray-800">Rp {activePlan?.transport_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-blue-50 border border-blue-100 rounded-lg">
                <span className="text-sm font-bold text-gray-900">Expected Total</span>
                <span className="text-xl font-bold text-blue-700">Rp {activePlan?.total_expected_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-green-50 border border-green-200 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-sm">💚</span>
                  <span className="text-xs font-semibold text-green-700 uppercase tracking-wider">Saving vs Baseline</span>
                </div>
                <p className="text-green-800 font-bold text-base">
                  Rp {planResult?.estimated_saving_vs_baseline?.toLocaleString('id-ID') || 0}
                </p>
                <p className="text-green-600 text-xs font-medium">{planResult?.estimated_saving_pct || 0}% saved</p>
              </div>
              <div className="bg-orange-50 border border-orange-200 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-sm">⚠️</span>
                  <span className="text-xs font-semibold text-orange-700 uppercase tracking-wider">Worst Case</span>
                </div>
                <p className="text-orange-800 font-bold text-base">Rp {activePlan?.worst_case_total_cost?.toLocaleString('id-ID') || 0}</p>
                <p className="text-orange-600 text-xs">Upper bound estimate</p>
              </div>
            </div>
          </div>
        </section>

      </main>

      <footer className="mt-8 pb-8 text-center text-gray-400 text-xs">
        Compfest Market Procurement · Frontend Demo
      </footer>
    </div>
  );
}
