'use client';

import { useState } from 'react';

// Gambar ilustrasi komoditas
const CabaiIcon = () => (
  <img src="https://via.placeholder.com/64x64.png?text=Cabai" alt="Cabai Merah" className="w-16 h-16" />
);

const BawangIcon = () => (
  <img src="https://via.placeholder.com/64x64.png?text=Bawang" alt="Bawang Merah" className="w-16 h-16" />
);

// Gambar ilustrasi pasar untuk header rekomendasi
const PasarHeaderIcon = () => (
  <img src="https://via.placeholder.com/128x128.png?text=Pasar+Tradisional" alt="Ilustrasi Pasar" className="w-32 h-32" />
);

export default function Home() {
  const [location, setLocation] = useState('Depok');
  const [deadline, setDeadline] = useState('2026-08-24');
  const [strategy, setStrategy] = useState('Balanced');
  const [showResult, setShowResult] = useState(false);

  const handleFindPlan = (e: React.FormEvent) => {
    e.preventDefault();
    setShowResult(true);
  };

  return (
    <div className="min-h-screen bg-[#fcf8f0] text-gray-900 p-8 font-mono">
      <header className="mb-10 border-b-2 border-dashed border-[#e6c1a8] pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-widest text-[#8c5a45]">LOGO / PRODUCT NAME</h1>
          <p className="text-gray-700 mt-2 text-lg">Smarter Food Procurement</p>
        </div>
        <div className="flex space-x-2">
            <span className="text-3xl">🌶️</span>
            <span className="text-3xl">🧅</span>
            <span className="text-3xl">🧺</span>
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
              <label className="block mb-2 text-sm text-gray-600">Location</label>
              <input 
                type="text" 
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full bg-[#fcf8f0] border-2 border-[#e6c1a8] p-3 text-gray-900 focus:outline-none focus:border-[#c59c84] rounded-lg" 
              />
            </div>

            <div>
              <label className="block mb-2 text-sm text-gray-600">Shopping List</label>
              <div className="space-y-5 mb-5 border-l-4 border-[#e6c1a8] pl-5">
                <div className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                  <div className="flex items-center space-x-4">
                    <CabaiIcon />
                    <span className="text-lg font-semibold">Cabai Merah</span>
                  </div>
                  <div className="flex items-center text-lg">
                    <span className="mr-2">[</span>
                    <input type="number" defaultValue={10} className="w-16 bg-transparent text-center focus:outline-none text-gray-900 font-bold" />
                    <span className="ml-2">] kg</span>
                  </div>
                </div>
                <div className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                  <div className="flex items-center space-x-4">
                    <BawangIcon />
                    <span className="text-lg font-semibold">Bawang Merah</span>
                  </div>
                  <div className="flex items-center text-lg">
                    <span className="mr-2">[</span>
                    <input type="number" defaultValue={15} className="w-16 bg-transparent text-center focus:outline-none text-gray-900 font-bold" />
                    <span className="ml-2">] kg</span>
                  </div>
                </div>
              </div>
              <button type="button" className="text-[#8c5a45] hover:text-[#c59c84] transition-colors flex items-center space-x-2 font-bold">
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
                className="w-full bg-[#fcf8f0] border-2 border-[#e6c1a8] p-3 text-gray-900 focus:outline-none focus:border-[#c59c84] rounded-lg" 
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
          <h2 className="text-xl font-bold mb-8 text-[#8c5a45] border-b-2 border-dashed border-[#e6c1a8] pb-3 relative z-10">RECOMMENDED PLAN</h2>
          
          <div className="space-y-7 relative z-10">
            <div className="flex items-center space-x-6 border-b-2 border-[#e6c1a8] pb-6">
                <PasarHeaderIcon />
                <div>
                  <h3 className="text-gray-600 text-sm mb-1 font-semibold">Best option</h3>
                  <p className="text-2xl text-[#8c5a45] font-bold">Besok — Pasar Kramat Jati</p>
                </div>
            </div>

            <div className="border-l-4 border-[#e6c1a8] pl-5 space-y-4">
              <div className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                <div className="flex items-center space-x-3">
                    <span>🌶️</span>
                    <span className="text-lg">Cabai Merah</span>
                </div>
                <span className="text-lg font-bold">10 kg</span>
              </div>
              <div className="flex justify-between items-center bg-[#fefcf8] p-3 rounded-lg border border-[#e6c1a8]">
                 <div className="flex items-center space-x-3">
                    <span>🧅</span>
                    <span className="text-lg">Bawang Merah</span>
                </div>
                <span className="text-lg font-bold">15 kg</span>
              </div>
            </div>

            <div className="space-y-4 pt-4">
              <div className="flex justify-between items-center border-b-2 border-dashed border-[#e6c1a8] pb-3">
                <span className="text-gray-600 text-sm">Expected item cost</span>
                <span className="text-lg font-semibold">Rp 1.240.000</span>
              </div>
              <div className="flex justify-between items-center border-b-2 border-dashed border-[#e6c1a8] pb-3">
                <span className="text-gray-600 text-sm">Transport</span>
                <span className="text-lg font-semibold">Rp 45.000</span>
              </div>
              <div className="flex justify-between items-center border-b-2 border-[#e6c1a8] pb-3 bg-[#fff8e1] p-3 rounded-lg">
                <span className="text-gray-900 text-base font-bold">Expected total</span>
                <span className="text-[#8c5a45] font-bold text-2xl">Rp 1.285.000</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-6">
              <div className="bg-[#e8f5e9] p-4 rounded-xl border border-[#a5d6a7]">
                <span className="block text-gray-700 text-sm mb-1">Saving</span>
                <span className="text-green-700 font-bold text-lg">Rp 172.000 (11.8%)</span>
              </div>
              <div className="bg-[#fff3e0] p-4 rounded-xl border border-[#ffcc80]">
                <span className="block text-gray-700 text-sm mb-1">Price risk</span>
                <span className="text-orange-700 font-bold text-lg">MEDIUM</span>
              </div>
            </div>

            <div className="pt-8 mt-auto">
              <button className="w-full border-2 border-[#8c5a45] p-4 text-center text-[#8c5a45] hover:text-white hover:bg-[#c59c84] hover:border-[#c59c84] transition-colors rounded-xl flex justify-between items-center text-lg font-bold shadow-sm">
                <span>[ View Alternative ]</span>
                <span className="border-2 border-[#e6c1a8] rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold bg-[#fcf8f0]">↓</span>
              </button>
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