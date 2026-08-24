'use client';

import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix for default marker icons in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

interface MapPickerProps {
  location: [number | string, number | string];
  onChange: (loc: [number, number]) => void;
}

function LocationMarker({ location, onChange }: MapPickerProps) {
  useMapEvents({
    click(e) {
      onChange([e.latlng.lat, e.latlng.lng]);
    },
  });

  const position: [number, number] | null = 
    typeof location[0] === 'number' && typeof location[1] === 'number' && !isNaN(location[0]) && !isNaN(location[1])
      ? [location[0], location[1]]
      : null;

  return position === null ? null : (
    <Marker position={position}></Marker>
  );
}

export default function MapPicker({ location, onChange }: MapPickerProps) {
  // Default to Jakarta if no valid location is provided yet
  const center: [number, number] = 
    typeof location[0] === 'number' && typeof location[1] === 'number' && !isNaN(location[0]) && !isNaN(location[1])
      ? [location[0], location[1]]
      : [-6.2, 106.8];

  return (
    <MapContainer center={center} zoom={11} className="w-full h-[250px] z-0">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <LocationMarker location={location} onChange={onChange} />
    </MapContainer>
  );
}
