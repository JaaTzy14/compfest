'use client';

import { useState } from 'react';

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
  // Menggunakan koordinat array langsung sesuai format backend [-6.2, 106.8]
  const [location, setLocation] = useState<[number, number]>([-6.2, 106.8]);
  const [deadline, setDeadline] = useState('2026-08-20');
  const [strategy, setStrategy] = useState('Balanced');
  
  const [planResult, setPlanResult] = useState<PlanResult | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState<string | null>(null);

  const [items, setItems] = useState([
    { id: 8, name: "Cabe Merah Keriting", qty: 10, icon: "🌶️" },
    { id: 10, name: "Cabe Rawit Merah", qty: 5, icon: "🌶️" }
  ]);

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
      location: location, // Mengirim array [lat, lon] dengan benar
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
    <div className="min-h-screen bg-[#fcf8f0] text-gray-900 p-8 font-mono">
      <header className="mb-10 border-b-2 border-dashed border-[#e6c1a8] pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-widest text-[#8c5a45]">LOGO / PRODUCT NAME</h1>
          <p className="text-gray-700 mt-2 text-lg">Smarter Food Procurement</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <button
              type="button"
              onClick={handleRefreshData}
              disabled={isRefreshing}
              className="bg-[#8c5a45] border-2 border-[#8c5a45] px-4 py-2 text-white hover:bg-[#c59c84] hover:border-[#c59c84] disabled:opacity-60 disabled:cursor-not-allowed transition-colors rounded-lg text-sm font-bold shadow-md"
            >
              {isRefreshing ? '[ Refreshing... ]' : '[ Refresh Data ]'}
            </button>
            {refreshStatus && (
              <p className="mt-2 text-xs text-gray-600 max-w-64">{refreshStatus}</p>
            )}
          </div>
          <div className="flex space-x-2">
            <span className="text-3xl">🌶️</span>
            <span className="text-3xl">🧅</span>
            <span className="text-3xl">🧺</span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 lg:gap-16">
        
        {/* KOLOM KIRI: YOUR PROCUREMENT */}
        <section className="bg-white border-4 border-[#e6c1a8] p-8 rounded-xl shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 opacity-10">
              <span className="text-9xl">📋</span>
          </div>
          <h2 className="text-xl font-bold mb-8 text-[#8c5a45] border-b-2 border-dashed border-[#e6c1a8] pb-3 relative z-10">YOUR PROCUREMENT</h2>
          
          <form onSubmit={handleFindPlan} className="space-y-7 relative z-10">
            <div>
              <label className="block mb-2 text-sm text-gray-600">Location Coordinates [Lat, Lon]</label>
              <div className="flex space-x-2">
                <input 
                  type="number" 
                  step="any"
                  value={location[0]}
                  onChange={(e) => setLocation([parseFloat(e.target.value) || 0, location[1]])}
                  className="w-1/2 bg-[#fcf8f0] border-2 border-[#e6c1a8] p-3 text-gray-900 focus:outline-none focus:border-[#c59c84] rounded-lg font-bold" 
                  placeholder="Latitude"
                />
                <input 
                  type="number" 
                  step="any"
                  value={location[1]}
                  onChange={(e) => setLocation([location[0], parseFloat(e.target.value) || 0])}
                  className="w-1/2 bg-[#fcf8f0] border-2 border-[#e6c1a8] p-3 text-gray-900 focus:outline-none focus:border-[#c59c84] rounded-lg font-bold" 
                  placeholder="Longitude"
                />
              </div>
            </div>

            <div>
              <label className="block mb-2 text-sm text-gray-600">Shopping List</label>
              <div className="space-y-4 mb-5 border-l-4 border-[#e6c1a8] pl-5">
                
                {items.map((item, index) => (
                  <div key={index} className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                    <div className="flex items-center space-x-3 w-1/2">
                      <span className="text-2xl">{item.icon}</span>
                      <select 
                        value={item.id}
                        onChange={(e) => handleItemChange(index, e.target.value)}
                        className="bg-transparent font-semibold text-lg focus:outline-none w-full text-gray-900 cursor-pointer"
                      >
                        {CATALOG.map((cat) => (
                           <option key={cat.id} value={cat.id}>{cat.name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="flex items-center text-lg">
                      <span className="mr-2 text-gray-400">[</span>
                      <input 
                        type="number" 
                        min="1"
                        value={item.qty}
                        onChange={(e) => handleQtyChange(index, e.target.value)}
                        className="w-12 bg-transparent text-center focus:outline-none text-gray-900 font-bold" 
                      />
                      <span className="ml-2 text-gray-400">] kg</span>
                      <button 
                        type="button" 
                        onClick={() => handleRemoveItem(index)}
                        className="ml-4 text-red-400 hover:text-red-600 text-sm font-bold border border-red-200 rounded p-1 bg-red-50"
                        title="Remove Item"
                      >
                        X
                      </button>
                    </div>
                  </div>
                ))}

              </div>
              <button 
                type="button" 
                onClick={handleAddItem}
                className="text-[#8c5a45] hover:text-[#c59c84] transition-colors flex items-center space-x-2 font-bold p-2 hover:bg-[#fcf8f0] rounded-lg"
              >
                  <span>🧺</span>
                  <span>[+ Add Item]</span>
              </button>
            </div>

            <div>
              <label className="block mb-2 text-sm text-gray-600">Deadline</label>
              <input 
                type="date" 
                value={deadline}
                onChange={(e) => setDeadline(e.target.value)}
                className="w-full bg-[#fcf8f0] border-2 border-[#e6c1a8] p-3 text-gray-900 focus:outline-none focus:border-[#c59c84] rounded-lg font-bold" 
              />
            </div>

            <div>
              <label className="block mb-2 text-sm text-gray-600">Strategy</label>
              <div className="space-y-3">
                {[
                  { name: 'Cheapest', icon: '💰' },
                  { name: 'Balanced', icon: '⚖️' },
                  { name: 'Low Risk', icon: '🛡️' },
                ].map((opt) => (
                  <label key={opt.name} className="flex items-center space-x-4 cursor-pointer p-3 rounded-lg border border-[#e6c1a8] hover:bg-[#fcf8f0] transition-colors">
                    <input 
                      type="radio" 
                      name="strategy" 
                      value={opt.name}
                      checked={strategy === opt.name}
                      onChange={(e) => setStrategy(e.target.value)}
                      className="form-radio text-[#8c5a45] focus:ring-0 bg-transparent border-[#e6c1a8] w-5 h-5"
                    />
                    <div className="flex items-center space-x-3">
                        <span className="text-2xl">{opt.icon}</span>
                        <span className={`text-lg ${strategy === opt.name ? 'text-[#8c5a45] font-bold' : 'text-gray-700'}`}>{opt.name}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="pt-8">
              <button 
                type="submit" 
                className="w-full bg-[#8c5a45] border-2 border-[#8c5a45] p-4 text-center hover:bg-[#c59c84] hover:border-[#c59c84] text-white transition-colors rounded-xl text-lg font-bold shadow-md"
              >
                [ Find Best Plan ]
              </button>
            </div>
          </form>
        </section>

        {/* KOLOM KANAN: RECOMMENDED PLAN */}
        <section className={`bg-white border-4 border-[#e6c1a8] p-8 rounded-xl shadow-lg transition-all duration-700 relative overflow-hidden ${showResult ? 'opacity-100' : 'opacity-20'}`}>
          <div className="absolute top-0 right-0 w-32 h-32 opacity-10">
              <span className="text-9xl">🌟</span>
          </div>
          <h2 className="text-xl font-bold mb-8 text-[#8c5a45] border-b-2 border-dashed border-[#e6c1a8] pb-3 relative z-10">RECOMMENDED PLAN ({strategy})</h2>
          
          <div className="space-y-7 relative z-10">
            <div className="flex items-center space-x-6 border-b-2 border-[#e6c1a8] pb-6">
                <span className="text-7xl">🏘️</span>
                <div>
                  <h3 className="text-gray-600 text-sm mb-1 font-semibold">Best option market</h3>
                  <p className="text-2xl text-[#8c5a45] font-bold">
                    {activePlan?.lines && activePlan.lines.length > 0 ? activePlan.lines[0].market_name : "Pilih dan klik Find Best Plan"}
                  </p>
                </div>
            </div>

            <div className="border-l-4 border-[#e6c1a8] pl-5 space-y-4">
              {activePlan?.lines?.map((line: PlanLine, idx: number) => (
                <div key={idx} className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                  <div className="flex items-center space-x-3">
                      <span>🛒</span>
                      <div>
                        <p className="text-base font-bold">{line.commodity}</p>
                        <p className="text-xs text-gray-500">{line.target_date} — Rp {line.expected_price_per_kg?.toLocaleString('id-ID')}/kg</p>
                      </div>
                  </div>
                  <span className="text-lg font-bold">{line.qty_kg} kg</span>
                </div>
              ))}
            </div>

            <div className="space-y-4 pt-4">
              <div className="flex justify-between items-center border-b-2 border-dashed border-[#e6c1a8] pb-3">
                <span className="text-gray-600 text-sm">Expected item cost</span>
                <span className="text-lg font-semibold">Rp {activePlan?.purchase_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
              <div className="flex justify-between items-center border-b-2 border-dashed border-[#e6c1a8] pb-3">
                <span className="text-gray-600 text-sm">Transport</span>
                <span className="text-lg font-semibold">Rp {activePlan?.transport_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
              <div className="flex justify-between items-center border-b-2 border-[#e6c1a8] pb-3 bg-[#fff8e1] p-3 rounded-lg">
                <span className="text-gray-900 text-base font-bold">Expected total</span>
                <span className="text-[#8c5a45] font-bold text-2xl">Rp {activePlan?.total_expected_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-6">
              <div className="bg-[#e8f5e9] p-4 rounded-xl border border-[#a5d6a7]">
                <span className="block text-gray-700 text-sm mb-1">Saving vs Baseline</span>
                <span className="text-green-700 font-bold text-lg">
                  Rp {planResult?.estimated_saving_vs_baseline?.toLocaleString('id-ID') || 0} ({planResult?.estimated_saving_pct || 0}%)
                </span>
              </div>
              <div className="bg-[#fff3e0] p-4 rounded-xl border border-[#ffcc80]">
                <span className="block text-gray-700 text-sm mb-1">Worst Case Total</span>
                <span className="text-orange-700 font-bold text-base">Rp {activePlan?.worst_case_total_cost?.toLocaleString('id-ID') || 0}</span>
              </div>
            </div>
          </div>
        </section>

      </main>
      
      <footer className="mt-16 pt-6 border-t-2 border-dashed border-[#e6c1a8] text-center text-gray-600">
          Compfest Market Procurement - Frontend Demo
      </footer>
    </div>
  );
}
